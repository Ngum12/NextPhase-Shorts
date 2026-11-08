import ctypes
import os
from pathlib import Path
import subprocess
import sys
import pytest
from app import render_sandbox as sandbox
from app.media import render_baseline
from app.worker_limits import require_unprivileged


def test_required_mode_enforces_or_explicitly_refuses_this_kernel():
    if sandbox.supported():sandbox.require_support()
    else:
        with pytest.raises(RuntimeError,match='Landlock'):sandbox.require_support()


@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux seccomp filter test')
def test_seccomp_actually_denies_network_sockets():
    path=Path(sandbox.__file__).resolve()
    code=f"""import ctypes,socket,importlib.util
spec=importlib.util.spec_from_file_location('sandbox',{str(path)!r})
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
libc=ctypes.CDLL(None,use_errno=True)
assert libc.prctl(38,1,0,0,0)==0
module.network_filter(libc)
try:socket.socket()
except PermissionError:pass
else:raise SystemExit(1)
"""
    subprocess.run([sys.executable,'-I','-c',code],check=True,timeout=10)


def test_root_cannot_satisfy_unprivileged_worker_guard(monkeypatch):
    import app.worker_limits as limits
    monkeypatch.setattr(limits.sys,'platform','linux');monkeypatch.setattr(limits.os,'geteuid',lambda:0,raising=False)
    with pytest.raises(RuntimeError,match='unprivileged'):require_unprivileged()


def test_real_baseline_under_filesystem_sandbox_when_host_supports_it(tmp_path,monkeypatch):
    if not sandbox.supported():
        # This proves refusal, not successful isolation. Actual host acceptance
        # stays open; CI on supported kernels also runs the real media path below.
        with pytest.raises(RuntimeError):sandbox.require_support()
        return
    source=tmp_path/'input.mp4';dest=tmp_path/'attempt'/'output.mp4'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=30',
        '-t','1','-c:v','libx264',str(source)],check=True,timeout=30)
    monkeypatch.setenv('WORKER_REQUIRE_SANDBOX','true')
    result=render_baseline(source,dest,1)
    assert result['width']==1080 and result['height']==1920 and result['duration']<=1


@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux process-group teardown')
def test_probe_teardown_kills_descendants_even_when_probe_parent_already_exited(tmp_path,monkeypatch):
    import time
    from app.media import probe_video,MediaError
    from test_worker_resilience import running
    marker=tmp_path/'descendant-pid';fake=tmp_path/'ffprobe'
    fake.write_text(f'#!{sys.executable}\nimport subprocess,sys\nfrom pathlib import Path\np=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\nPath(sys.argv[-1]).write_text(str(p.pid))\nprint("{{}}")\n')
    fake.chmod(0o700);monkeypatch.setenv('PATH',str(tmp_path)+os.pathsep+os.environ['PATH'])
    pid=None
    try:
        with pytest.raises(MediaError):probe_video(marker)
        pid=int(marker.read_text());deadline=__import__('time').monotonic()+5
        while running(pid) and time.monotonic()<deadline:time.sleep(.02)
        assert not running(pid)
    finally:
        if pid and running(pid):os.kill(pid,9)
