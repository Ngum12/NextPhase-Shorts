"""Operator-only preview of one reviewed candidate; no API/worker integration."""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .analysis_plan import Proposal, planning_edl
from .local_transcription import file_digest, regular_file
from .media import decoder_invocation, probe_video, run_render, teardown_decoder
from .media_policy import CODEC_THREADS, input_args

MAX_SOURCE = 314572800
MAX_OUTPUT = 64 * 1024**2


def output_frames(path):
    """Count decoded frames and verify the encoded frame rate; bounded local file."""
    command, env, kwargs = decoder_invocation([
        'ffprobe', '-v', 'error', *input_args(), '-select_streams', 'v:0',
        '-count_frames', '-show_entries', 'stream=nb_read_frames,avg_frame_rate',
        '-of', 'json', str(path)], 60)
    with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, env=env, close_fds=True, **kwargs) as child:
        try:
            raw, _ = child.communicate(timeout=60)
            if child.returncode:
                raise RuntimeError('Preview frame inspection failed')
        finally:
            teardown_decoder(child)
    stream = json.loads(raw)['streams'][0]
    if stream['avg_frame_rate'] != '30/1':
        raise RuntimeError('Preview frame rate differs')
    return int(stream['nb_read_frames'])


def preview(*, source, proposal, candidate, output, acknowledge=False):
    if os.getenv('APP_ENV', 'development') not in ('development', 'test'):
        raise RuntimeError('Preview pilot requires development/test mode')
    if os.getenv('WORKER_REQUIRE_SANDBOX', 'false').lower() == 'true':
        raise RuntimeError('Preview pilot is not enabled in required worker mode')
    if not acknowledge:
        raise RuntimeError('Review acknowledgement required')
    source = regular_file(source, maximum=MAX_SOURCE)
    proposal = regular_file(proposal, maximum=1024**2)
    data = proposal.read_bytes()
    plan = Proposal.model_validate_json(data)
    if type(candidate) is not int or not 1 <= candidate <= len(plan.candidates):
        raise RuntimeError('Choose an available candidate')
    selected = plan.candidates[candidate - 1]
    output = Path(output).absolute()
    if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
           for p in (output, *output.parents)):
        raise RuntimeError('Use a new private output directory')
    output.mkdir(mode=0o700)
    try:
        with tempfile.TemporaryDirectory(prefix='preview-', dir=output) as scratch:
            # Decode this private snapshot, whose hash we actually verified.
            # Never decode a mutable original after checking a different byte stream.
            snapshot = Path(scratch) / 'source.mp4'
            with source.open('rb') as original, snapshot.open('xb') as copied:
                os.chmod(snapshot, 0o600)
                total = 0
                while chunk := original.read(1024**2):
                    total += len(chunk)
                    if total > MAX_SOURCE:
                        raise RuntimeError('Source exceeds preview bound')
                    copied.write(chunk)
            if file_digest(snapshot) != plan.source_sha256:
                raise RuntimeError('Preview source identity differs')
            metadata = probe_video(snapshot)
            if (math.ceil(metadata['duration'] * 1000) != plan.source_duration_ms
                    or metadata['duration'] > 600):
                raise RuntimeError('Preview source duration differs')
            destination = output / 'preview.mp4'
            with destination.open('xb'):
                os.chmod(destination, 0o600)
            frames = selected.output_frames
            seconds = frames / 30
            # All commands/filters are fixed server code. JSON supplies only
            # validated numeric bounds, never filters, paths or command fragments.
            command = ['ffmpeg', '-nostdin', '-v', 'error', '-y', '-max_alloc', '67108864',
                '-filter_threads', str(CODEC_THREADS), *input_args(), '-i', str(snapshot),
                '-ss', f'{selected.source_start_ms / 1000:.3f}', '-t', f'{seconds:.6f}',
                '-map', '0:v:0', '-map', '0:a:0?', '-sn', '-dn',
                '-map_metadata', '-1', '-map_chapters', '-1',
                '-vf', 'scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,'
                       'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,fps=30,setsar=1,format=yuv420p',
                '-c:v', 'libx264', '-threads', str(CODEC_THREADS), '-preset', 'veryfast',
                '-crf', '24', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
                '-ar', '48000', '-ac', '2', '-movflags', '+faststart',
                '-max_muxing_queue_size', '1024', str(destination)]

            def size_guard():
                if destination.stat().st_size >= MAX_OUTPUT:
                    raise RuntimeError('Preview output exceeds bound')
                return False

            run_render(command, 300, size_guard, max_file_bytes=MAX_OUTPUT)
            size_guard()
            info = probe_video(destination)
            if (info['width'] != 1080 or info['height'] != 1920
                    or info['duration'] > min(60, plan.requested_seconds)
                    or abs(info['duration'] - seconds) > 1/30
                    or output_frames(destination) != frames):
                raise RuntimeError('Preview output failed validation')
            report = {'ok': True, 'candidate': candidate, 'source_sha256': plan.source_sha256,
                'proposal_sha256': hashlib.sha256(data).hexdigest(),
                'human_annotations_applied': plan.review_sha256 is not None,
                'review_sha256': plan.review_sha256, 'transcript_sha256': plan.transcript_sha256,
                'preview_sha256': file_digest(destination), 'output_frames': frames,
                'duration_seconds': info['duration'], 'width': 1080, 'height': 1920, 'fps': 30,
                'source_start_ms': selected.source_start_ms, 'source_end_ms': selected.source_end_ms,
                'human_review_required': True, 'meaning_verified': False,
                'live_app_changed': False, 'audio_video_cut_review_required': True,
                'scope': 'operator preview; letterbox only, no captions or intelligent reframing'}
            for name, value in (('preview-report.json', report),
                                ('reviewed-proposed-edl.json', planning_edl(plan, candidate - 1))):
                with (output / name).open('x', encoding='utf-8') as handle:
                    os.chmod(output / name, 0o600)
                    json.dump(value, handle, indent=2)
            return report
    except BaseException:
        shutil.rmtree(output)
        raise
