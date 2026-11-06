"""Minimal safe ffprobe/FFmpeg operations; no shell, no user-controlled filters."""
import json
import subprocess
from pathlib import Path
from .config import get_settings

class MediaError(Exception):
    pass

def probe_video(path: Path) -> dict:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=index,codec_type,width,height",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        )
        data = json.loads(result.stdout)
        streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
        duration = float(data.get("format", {}).get("duration", 0))
        if not streams or not 0 < duration < 86400:
            raise MediaError("Not a valid video with a known duration")
        video = streams[0]
        width, height = int(video.get("width", 0)), int(video.get("height", 0))
        if not (16 <= width <= 7680 and 16 <= height <= 7680):
            raise MediaError("Unsupported video dimensions")
        return {"duration": duration, "width": width, "height": height}
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise MediaError("Could not inspect the uploaded media") from exc

def render_baseline(source: Path, dest: Path, seconds: int) -> dict:
    """Stage 1 baseline only: first seconds, centered letterbox, safe AAC/H.264, vertical 30fps.

    This is NOT AI editing. Phase 2+ adds a structured timeline and professional effects.
    """
    if not (1 <= seconds <= 60):
        raise MediaError("Duration must be 1–60 seconds")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.stem + ".partial.mp4")
    tmp.unlink(missing_ok=True)
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,"
        "fps=30,setsar=1,format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-t", str(max(0.5, seconds - 0.10)), "-map", "0:v:0", "-map", "0:a?", "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart",
        "-max_muxing_queue_size", "1024", str(tmp),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=get_settings().render_timeout_seconds)
        info = probe_video(tmp)
        if info["width"] != 1080 or info["height"] != 1920 or info["duration"] > float(seconds) or info["duration"] > 60.0:
            raise MediaError("Rendered video failed aspect ratio or duration check")
        tmp.replace(dest)
        return info
    except subprocess.TimeoutExpired as exc:
        raise MediaError("Video render timed out") from exc
    except subprocess.CalledProcessError as exc:
        raise MediaError("Video rendering failed") from exc
    finally:
        tmp.unlink(missing_ok=True)
