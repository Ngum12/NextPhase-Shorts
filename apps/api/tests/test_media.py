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


@pytest.mark.skipif(shutil.which('ffmpeg') is None or shutil.which('ffprobe') is None,
                    reason='ffmpeg not installed')
def test_full_60_second_export_never_exceeds_cap(tmp_path):
    source = tmp_path / 'long.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi',
                    '-i', 'color=c=navy:s=160x90:r=30', '-f', 'lavfi',
                    '-i', 'sine=frequency=440:sample_rate=48000', '-t', '61',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)],
                   check=True, timeout=30)
    output = tmp_path / 'capped.mp4'
    info = render_baseline(source, output, 60)
    assert (info['width'], info['height']) == (1080, 1920)
    assert 59 <= info['duration'] <= 60.0


def test_cancellation_kills_ffmpeg_and_removes_partial_output(tmp_path, monkeypatch):
    from app.media import MediaCancelled
    source = tmp_path / 'cancel-source.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi',
                    '-i', 'color=c=navy:s=160x90:r=30', '-t', '60', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', str(source)], check=True, timeout=30)
    real_popen = subprocess.Popen
    children = []
    def record_popen(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        if args[0][0]=='ffmpeg':children.append(child)
        return child
    monkeypatch.setattr('app.media.subprocess.Popen', record_popen)
    checks = 0
    def should_cancel():
        nonlocal checks
        checks += 1
        return checks >= 3
    output = tmp_path / 'cancelled.mp4'
    with pytest.raises(MediaCancelled):
        render_baseline(source, output, 60, should_cancel=should_cancel)
    assert len(children) == 1
    assert children[0].poll() is not None
    assert not output.exists()
    assert not output.with_name('cancelled.partial.mp4').exists()


def test_output_limit_fails_instead_of_accepting_a_truncated_video(tmp_path):
    from app.media import OutputLimitExceeded
    source=tmp_path/'limited-source.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=30',
        '-t','3','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True,timeout=30)
    output=tmp_path/'limited.mp4'
    with pytest.raises(OutputLimitExceeded):render_baseline(source,output,3,max_output_bytes=1024)
    assert not output.exists() and not output.with_name('limited.partial.mp4').exists()
