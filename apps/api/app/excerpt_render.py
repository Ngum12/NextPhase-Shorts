"""Fixed, frame-checked excerpt renderer shared by operator and queued previews."""
import json
import os
from pathlib import Path
import subprocess

from .media import (MediaCancelled, MediaError, OutputLimitExceeded, decoder_invocation,
                    probe_video, run_render, teardown_decoder)
from .media_policy import CODEC_THREADS, input_args
from .observability import stage


def output_frames(path):
    command, env, kwargs = decoder_invocation([
        'ffprobe', '-v', 'error', *input_args(), '-select_streams', 'v:0',
        '-count_frames', '-show_entries', 'stream=nb_read_frames,avg_frame_rate',
        '-of', 'json', str(path)], 60)
    with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, env=env, close_fds=True, **kwargs) as child:
        try:
            raw, _ = child.communicate(timeout=60)
            if child.returncode:raise MediaError('Preview frame inspection failed')
        finally:teardown_decoder(child)
    try:
        stream = json.loads(raw)['streams'][0]
        if stream['avg_frame_rate'] != '30/1':raise ValueError()
        return int(stream['nb_read_frames'])
    except (ValueError,KeyError,IndexError,TypeError):
        raise MediaError('Preview frame inspection failed') from None


def render_excerpt(source, destination, *, start_ms, end_ms, frames, requested_seconds,
                   max_output_bytes, should_cancel=lambda:False, timeout=300):
    if (any(type(n) is not int for n in (start_ms,end_ms,frames,requested_seconds))
            or not 0<=start_ms<end_ms<=600000 or not 5<=requested_seconds<=60
            or end_ms-start_ms>requested_seconds*1000
            or not 150<=frames<=requested_seconds*30
            or frames!=(end_ms-start_ms)*30//1000):
        raise MediaError('Invalid preview interval')
    if should_cancel():raise MediaCancelled('Preview cancelled')
    source=Path(source);destination=Path(destination)
    destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if destination.exists() or destination.is_symlink():raise MediaError('Preview output exists')
    temporary=destination.with_name(destination.stem+'.partial.mp4')
    with temporary.open('xb'):
        os.chmod(temporary,0o600)
    seconds=frames/30
    command=['ffmpeg','-nostdin','-v','error','-y','-max_alloc','67108864',
        '-filter_threads',str(CODEC_THREADS),*input_args(),'-i',str(source),
        '-ss',f'{start_ms/1000:.3f}','-t',f'{seconds:.6f}',
        '-map','0:v:0','-map','0:a:0?','-sn','-dn','-map_metadata','-1','-map_chapters','-1',
        '-vf','scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,'
              'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,fps=30,setsar=1,format=yuv420p',
        '-c:v','libx264','-threads',str(CODEC_THREADS),'-preset','veryfast','-crf','24',
        '-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-ar','48000','-ac','2',
        '-movflags','+faststart','-max_muxing_queue_size','1024',str(temporary)]
    try:
        def guard():
            if temporary.stat().st_size>=max_output_bytes:
                raise OutputLimitExceeded('Preview output exceeds bound')
            return should_cancel()
        with stage('encode') as observed:
            observed.update(run_render(command,timeout,guard,max_file_bytes=max_output_bytes) or {})
        if guard():raise MediaCancelled('Preview cancelled')
        with stage('output_probe'):
            info=probe_video(temporary)
            if (info['width']!=1080 or info['height']!=1920
                    or info['duration']>min(60,requested_seconds)
                    or abs(info['duration']-seconds)>1/30 or output_frames(temporary)!=frames):
                raise MediaError('Preview output failed validation')
        if should_cancel():raise MediaCancelled('Preview cancelled before publication')
        temporary.replace(destination)
        return info
    except subprocess.SubprocessError:
        raise MediaError('Preview rendering failed') from None
    finally:temporary.unlink(missing_ok=True)
