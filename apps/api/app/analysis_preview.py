"""Operator preview wrapper; queued jobs share the fixed excerpt renderer."""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile

from .analysis_plan import Proposal, planning_edl
from .local_transcription import file_digest, regular_file
from .media import probe_video
from .excerpt_render import render_excerpt

MAX_SOURCE = 314572800
MAX_OUTPUT = 64 * 1024**2


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
            frames = selected.output_frames
            info = render_excerpt(snapshot,destination,start_ms=selected.source_start_ms,
                end_ms=selected.source_end_ms,frames=frames,requested_seconds=plan.requested_seconds,
                max_output_bytes=MAX_OUTPUT)
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
