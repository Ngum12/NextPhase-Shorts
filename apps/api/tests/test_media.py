import shutil
import subprocess
from pathlib import Path
import pytest
from app.media import probe_video, render_baseline, MediaError

@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                    reason="ffmpeg not installed")
def test_cloud_render_vertical_under_limit(tmp_path: Path):
    source = tmp_path / "input.mp4"
    out = tmp_path / "result.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=320x180:rate=15", "-t", "2", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(source)], check=True, timeout=30)
    info = render_baseline(source, out, 2)
    assert out.is_file()
    assert info["width"] == 1080 and info["height"] == 1920
    assert 0 < info["duration"] <= 2.2


def test_invalid_duration_no_render(tmp_path: Path):
    with pytest.raises(MediaError):
        render_baseline(tmp_path / "missing.mp4", tmp_path / "output.mp4", 61)
