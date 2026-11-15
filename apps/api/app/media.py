"""Minimal safe ffprobe/FFmpeg operations; no shell, no user-controlled filters."""
import json
import math
import os
import signal
import subprocess
import sys
import time
from typing import Callable
from pathlib import Path
from .config import get_settings
from .observability import stage,active_attributes
from .resource_measure import DecoderSamples, EncodeProgress
from .media_policy import CODEC_THREADS, input_args, validate_metadata

class MediaError(Exception):
    pass

class RenderDeadlineExceeded(MediaError):
    pass

class OutputLimitExceeded(MediaError):
    pass

class MediaCancelled(MediaError):
    pass


def teardown_decoder(process):
    if os.name=='posix':
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    elif process.poll() is None:process.kill()
    process.wait(timeout=5)


def decoder_invocation(cmd,timeout,max_file_bytes=None,read_files=(),address_limit_bytes=None,media_files=()):
    # Read only the explicit guard flag here; decoder-launch tests and tools do
    # not need to initialize server credentials just to construct a subprocess.
    sandbox_required=os.getenv('WORKER_REQUIRE_SANDBOX','false').lower()=='true'
    if address_limit_bytes is not None and (type(address_limit_bytes) is not int or
            not 134217728<=address_limit_bytes<=2147483648 or not sys.platform.startswith('linux')):
        raise MediaError('Bounded decoder needs a supported Linux address limit')
    # No JWT, database, S3, proxy or provider credentials reach the decoder.
    child_env={key:value for key,value in os.environ.items() if key.upper() in
               {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','TMPDIR','LANG','LC_ALL'}}
    child_env['PYTHONDONTWRITEBYTECODE']='1'
    child_cmd=cmd
    if sys.platform.startswith('linux'):
        # Absolute helper path also works with uvicorn --app-dir, which changes
        # sys.path without exporting PYTHONPATH. Isolated Python ignores user sites.
        sandbox=[]
        if address_limit_bytes is not None and cmd[0]=='ffmpeg' and max_file_bytes is None:
            raise MediaError('Bounded decoder needs a fixed output file bound')
        if sandbox_required:
            source=cmd[cmd.index('-i')+1] if cmd[0]=='ffmpeg' else cmd[-1]
            output=str(Path(cmd[-1]).resolve()) if cmd[0]=='ffmpeg' else None
            if cmd[0]=='ffmpeg' and max_file_bytes is None:raise MediaError('Strict renderer needs a fixed output file bound')
            sandbox=['--sandbox',json.dumps({'source':str(Path(source).resolve()),'output':output,
                'read_files':[str(Path(path).resolve(strict=True)) for path in read_files],
                'media_files':[str(Path(path).absolute()) for path in media_files]},separators=(',',':'))]
        child_cmd=[sys.executable,'-I',str(Path(__file__).with_name('render_child.py')),
                   str(os.getpid()),str(math.ceil(timeout*CODEC_THREADS+30)),
                   *(['--file-limit',str(max_file_bytes if cmd[0]=='ffmpeg' else 0)] if sandbox_required or address_limit_bytes is not None else []),
                   *(['--address-limit',str(address_limit_bytes)] if address_limit_bytes is not None else []),*sandbox,*cmd]
    elif sandbox_required:
        raise MediaError('Required decoder isolation needs supported Linux')
    kwargs={'start_new_session':True} if os.name=='posix' else {}
    return child_cmd,child_env,kwargs


def run_render(cmd, timeout, should_cancel, max_file_bytes=None, read_files=(),address_limit_bytes=None,capture_progress=False,media_files=()):
    if should_cancel():
        raise MediaCancelled('Render cancelled')
    started = time.monotonic()
    samples=DecoderSamples();progress=EncodeProgress() if capture_progress else None
    if capture_progress and (cmd[0]!='ffmpeg' or '-progress' not in cmd or cmd[cmd.index('-progress')+1]!='pipe:1'):
        raise MediaError('Invalid render progress configuration')
    child_cmd,child_env,kwargs=decoder_invocation(cmd,timeout,max_file_bytes,read_files,
        **({'media_files':media_files} if media_files else {}),
        **({'address_limit_bytes':address_limit_bytes} if address_limit_bytes is not None else {}))
    # Stderr is always discarded. Optional fixed progress counters use a bounded,
    # nonblocking stdout pipe; raw native output never enters logs or storage.
    with subprocess.Popen(child_cmd, stdin=subprocess.DEVNULL,stdout=subprocess.PIPE if capture_progress else subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=child_env,close_fds=True, **kwargs) as process:
        def drain_progress():
            if not capture_progress:return
            # Limit work and retained partial lines even if a damaged decoder
            # floods stdout. Pipe backpressure is bounded; raw bytes are discarded.
            for _ in range(4):
                try:chunk=os.read(process.stdout.fileno(),4096)
                except BlockingIOError:break
                if not chunk:break
                progress.feed(chunk)
        try:
            if capture_progress:os.set_blocking(process.stdout.fileno(),False)
            while True:
                samples.sample(process.pid)
                drain_progress()
                if should_cancel():
                    raise MediaCancelled('Render cancelled or lease lost')
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(cmd, timeout)
                try:
                    process.wait(timeout=min(0.25, remaining))
                    if process.returncode:
                        raise subprocess.CalledProcessError(process.returncode, cmd)
                    drain_progress()
                    return {**samples.attributes(),**(progress.attributes() if progress else {})}
                except subprocess.TimeoutExpired:
                    if time.monotonic() - started >= timeout:
                        raise
        finally:
            teardown_decoder(process)
            drain_progress()
            if active_attributes.get() is not None:
                active_attributes.get().update({**samples.attributes(),**(progress.attributes() if progress else {})})


def probe_video(path: Path, *, timeout=30) -> dict:
    if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=30:
        raise MediaError("Invalid media inspection deadline")
    try:
        cmd,env,kwargs=decoder_invocation(
            ["ffprobe", "-v", "error", "-max_alloc", "67108864", *input_args(), "-show_entries", "format=duration,format_name:stream=index,codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,sample_rate,channels:stream_disposition=attached_pic",
             "-of", "json", str(path)],timeout)
        with subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                text=True,env=env,close_fds=True,**kwargs) as process:
            try:
                output,_=process.communicate(timeout=timeout)
                if process.returncode:raise subprocess.CalledProcessError(process.returncode,cmd)
            finally:teardown_decoder(process)
        data = json.loads(output)
        return validate_metadata(data)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError, ZeroDivisionError, OverflowError, AttributeError, json.JSONDecodeError) as exc:
        raise MediaError("Could not inspect the uploaded media") from exc

def render_baseline(source: Path, dest: Path, seconds: int, *, max_output_bytes: int | None = None, should_cancel: Callable[[], bool] | None = None) -> dict:
    """Stage 1 baseline only: first seconds, centered letterbox, safe AAC/H.264, vertical 30fps.

    This is NOT AI editing. Phase 2+ adds a structured timeline and professional effects.
    """
    if not (1 <= seconds <= 60):
        raise MediaError("Duration must be 1–60 seconds")
    max_output_bytes = max_output_bytes or get_settings().max_render_bytes
    if should_cancel is not None and should_cancel():raise MediaCancelled('Render cancelled')
    with stage('source_probe'):
        source_info=probe_video(source)
    if source_info['duration']>get_settings().max_source_seconds:
        raise MediaError('Source exceeds the configured duration limit')
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.stem + ".partial.mp4")
    tmp.unlink(missing_ok=True)
    # Strict Landlock permits writing only this existing file, never creating
    # arbitrary scratch files. RLIMIT_FSIZE supplies the kernel file-size bound.
    if os.getenv('WORKER_REQUIRE_SANDBOX','false').lower()=='true':
        descriptor=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(descriptor)
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,"
        "fps=30,setsar=1,format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-max_alloc", "67108864", "-filter_threads", str(CODEC_THREADS),
        *input_args(), "-i", str(source),
        "-t", str(max(0.5, seconds - 0.10)), "-map", "0:v:0", "-map", "0:a?", "-vf", vf,
        "-c:v", "libx264", "-threads", str(CODEC_THREADS), "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart",
        "-max_muxing_queue_size", "1024", str(tmp),
    ]
    try:
        def stop_requested():
            if tmp.exists() and tmp.stat().st_size >= max_output_bytes:
                raise OutputLimitExceeded('Rendered file exceeded its reserved output limit')
            return should_cancel() if should_cancel is not None else False
        # Abort oversize output, never silently truncate it into a shorter export.
        with stage('encode') as observed:
            measurements=run_render(cmd, get_settings().render_timeout_seconds, stop_requested,max_file_bytes=max_output_bytes)
            observed.update(measurements or {})
        if tmp.stat().st_size >= max_output_bytes:
            raise OutputLimitExceeded('Rendered file exceeded its reserved output limit')
        with stage('output_probe') as qa:
            info = probe_video(tmp)
            qa['frames']=round(info['duration']*30)
            if observed.get('wall_seconds',0)>0:qa['frames_per_second']=qa['frames']/observed['wall_seconds']
        if info["width"] != 1080 or info["height"] != 1920 or info["duration"] > float(seconds) or info["duration"] > 60.0:
            raise MediaError("Rendered video failed aspect ratio or duration check")
        if should_cancel is not None and should_cancel():
            raise MediaCancelled('Render cancelled before publication')
        tmp.replace(dest)
        return info
    except subprocess.TimeoutExpired as exc:
        raise MediaError("Video render timed out") from exc
    except subprocess.CalledProcessError as exc:
        raise MediaError("Video rendering failed") from exc
    finally:
        tmp.unlink(missing_ok=True)
