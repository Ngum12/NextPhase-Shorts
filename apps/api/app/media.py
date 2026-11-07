"""Minimal safe ffprobe/FFmpeg operations; no shell, no user-controlled filters."""
import json
import subprocess
import time
from typing import Callable
from pathlib import Path
from .config import get_settings
from .media_policy import CODEC_THREADS, input_args, validate_metadata

class MediaError(Exception):
    pass

class OutputLimitExceeded(MediaError):
    pass

class MediaCancelled(MediaError):
    pass


def run_render(cmd, timeout, should_cancel):
    if should_cancel():
        raise MediaCancelled('Render cancelled')
    started = time.monotonic()
    with subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) as process:
        try:
            while True:
                if should_cancel():
                    raise MediaCancelled('Render cancelled or lease lost')
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(cmd, timeout)
                try:
                    _, stderr = process.communicate(timeout=min(0.25, remaining))
                    if process.returncode:
                        raise subprocess.CalledProcessError(process.returncode, cmd, stderr=stderr)
                    return
                except subprocess.TimeoutExpired:
                    if time.monotonic() - started >= timeout:
                        raise
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


def probe_video(path: Path) -> dict:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-max_alloc", "67108864", *input_args(), "-show_entries", "format=duration,format_name:stream=index,codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,sample_rate,channels:stream_disposition=attached_pic",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        )
        data = json.loads(result.stdout)
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
    source_info=probe_video(source)
    if source_info['duration']>get_settings().max_source_seconds:
        raise MediaError('Source exceeds the configured duration limit')
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.stem + ".partial.mp4")
    tmp.unlink(missing_ok=True)
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
        run_render(cmd, get_settings().render_timeout_seconds, stop_requested)
        if tmp.stat().st_size >= max_output_bytes:
            raise OutputLimitExceeded('Rendered file exceeded its reserved output limit')
        info = probe_video(tmp)
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
