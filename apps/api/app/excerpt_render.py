"""Fixed, frame-checked excerpt renderer shared by operator and queued previews."""
import json
import math
import os
import re
from pathlib import Path
import subprocess
import tempfile

from .media import (MediaCancelled, MediaError, OutputLimitExceeded, RenderDeadlineExceeded, decoder_invocation,
                    probe_video, run_render, teardown_decoder)
from .media_policy import CODEC_THREADS, input_args
from .observability import stage
from .caption_plan import validate_cues
from .preview_framing import framing_filter
from .polish import PolishSettings, caption_appearance, clip_audio_filter

PREVIEW_ENCODER_PRESET='superfast'

CAPTION_FONT=Path('/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf')


def caption_filters(cues, source, start_ms, polish=None):
    """Text stays in private UTF-8 files, outside FFmpeg's filter grammar."""
    filters=[];paths=[]
    size,color,position=caption_appearance(polish or PolishSettings())
    try:
        if not CAPTION_FONT.is_file():raise MediaError('Caption font is unavailable')
        for cue in cues:
            fd,name=tempfile.mkstemp(prefix='caption-',suffix='.txt',dir=source.parent)
            path=Path(name);paths.append(path)
            with os.fdopen(fd,'w',encoding='utf-8') as handle:handle.write(cue.text)
            # Internal canonical paths only; reject filter punctuation rather
            # than attempting multilayer quoting of a configurable media root.
            if not re.fullmatch(r'/[A-Za-z0-9_./-]+',str(path)):
                raise MediaError('Caption preview needs a canonical Linux media path')
            begin=(start_ms+cue.start_ms)/1000
            end=(start_ms+cue.end_ms)/1000
            filters.append(f"drawtext=fontfile={CAPTION_FONT}:textfile={path}:expansion=none:"
                f"fontsize={size}:fontcolor={color}:box=1:boxcolor=black@0.82:boxborderw=18:"
                f"line_spacing=12:x=(w-text_w)/2:y={position}:"
                f"enable='gte(t,{begin:.3f})*lt(t,{end:.3f})'")
        return filters,paths
    except BaseException:
        for path in paths:path.unlink(missing_ok=True)
        raise


def output_frames(path, *, timeout=60):
    if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=60:
        raise MediaError("Invalid frame inspection deadline")
    command, env, kwargs = decoder_invocation([
        'ffprobe', '-v', 'error', *input_args(), '-select_streams', 'v:0',
        '-count_frames', '-show_entries', 'stream=nb_read_frames,avg_frame_rate',
        '-of', 'json', str(path)], timeout)
    with subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, env=env, close_fds=True, **kwargs) as child:
        try:
            raw, _ = child.communicate(timeout=timeout)
            if child.returncode:raise MediaError('Preview frame inspection failed')
        finally:teardown_decoder(child)
    try:
        stream = json.loads(raw)['streams'][0]
        if stream['avg_frame_rate'] != '30/1':raise ValueError()
        return int(stream['nb_read_frames'])
    except (ValueError,KeyError,IndexError,TypeError):
        raise MediaError('Preview frame inspection failed') from None


def render_excerpt(source, destination, *, start_ms, end_ms, frames, requested_seconds,
                   max_output_bytes, should_cancel=lambda:False, timeout=300, captions=(), framing='fit', polish=None):
    polish=PolishSettings.model_validate(polish or {})
    try:
        geometry=framing_filter(framing).replace('fps=30,','')
    except ValueError:
        raise MediaError('Unsupported preview framing') from None
    captions=validate_cues(captions,frames)
    if (any(type(n) is not int for n in (start_ms,end_ms,frames,requested_seconds))
            or not 0<=start_ms<end_ms<=600000 or not 5<=requested_seconds<=60
            or end_ms-start_ms>requested_seconds*1000
            or not 150<=frames<=requested_seconds*30
            or frames!=(end_ms-start_ms)*30//1000):
        raise MediaError('Invalid preview interval')
    # Sample before fixed per-frame transforms, then drop preroll before scaling
    # and captions. Keep source PTS and two preroll frames: output-side -ss,
    # caption timing and audio fades keep their absolute source-clock behavior.
    preroll=max(0,start_ms*30//1000-2)/30
    video_filter=f'fps=30,trim=start={preroll:.9f},'+geometry
    if should_cancel():raise MediaCancelled('Preview cancelled')
    source=Path(source);destination=Path(destination)
    destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if destination.exists() or destination.is_symlink():raise MediaError('Preview output exists')
    temporary=destination.with_name(destination.stem+'.partial.mp4')
    with temporary.open('xb'):
        os.chmod(temporary,0o600)
    seconds=frames/30
    # Keep decoded keyframe preroll and original PTS; final output-side seeking
    # still owns the exact cut. Leveling retains full history for its gain state.
    input_seek=max(0,start_ms//1000-2) if polish.voice=='original' else 0
    command=['ffmpeg','-progress','pipe:1','-nostats','-nostdin','-v','error','-y','-max_alloc','67108864',
        '-filter_threads',str(CODEC_THREADS),'-copyts','-start_at_zero','-noaccurate_seek',
        '-ss',f'{input_seek:.3f}',*input_args(),'-i',str(source),
        '-ss',f'{start_ms/1000:.3f}','-t',f'{seconds:.6f}',
        '-map','0:v:0','-map','0:a:0?','-sn','-dn','-map_metadata','-1','-map_chapters','-1',
        '-vf',video_filter,
        '-c:v','libx264','-threads',str(CODEC_THREADS),'-preset',PREVIEW_ENCODER_PRESET,'-crf','24',
        '-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-ar','48000','-ac','2',
        '-movflags','+faststart','-max_muxing_queue_size','1024',str(temporary)]
    caption_paths=[]
    try:
        audio_filter=clip_audio_filter(polish,start_ms=start_ms,frames=frames)
        if audio_filter:
            command[-1:-1]=['-af',audio_filter]
        if captions:
            filters,caption_paths=caption_filters(captions,source,start_ms,polish)
            command[command.index('-vf')+1]+=','+','.join(filters)
        def guard():
            if temporary.stat().st_size>=max_output_bytes:
                raise OutputLimitExceeded('Preview output exceeds bound')
            return should_cancel()
        with stage('encode') as observed:
            caption_options={'read_files':caption_paths} if caption_paths else {}
            observed.update(run_render(command,timeout,guard,max_file_bytes=max_output_bytes,capture_progress=True,**caption_options) or {})
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
    except subprocess.TimeoutExpired:
        raise RenderDeadlineExceeded('Preview render exceeded its deadline') from None
    except subprocess.SubprocessError:
        raise MediaError('Preview rendering failed') from None
    finally:
        temporary.unlink(missing_ok=True)
        for path in caption_paths:path.unlink(missing_ok=True)
