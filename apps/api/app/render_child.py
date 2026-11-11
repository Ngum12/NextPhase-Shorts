"""Linux exec launcher: no server credentials, parent-death kill and OS limits.

Only fixed server FFmpeg/FFprobe invocations use this internal module. Required
mode also adds Landlock/seccomp restrictions; it still shares the host kernel.
"""
import ctypes
import os
import signal
import sys


def main():
    import resource
    expected_parent=int(sys.argv[1]);cpu_seconds=int(sys.argv[2]);command=sys.argv[3:]
    sandbox=None;file_limit=None
    if command and command[0]=='--file-limit':
        file_limit=int(command[1]);command=command[2:]
        if not 0<=file_limit<=536870912:raise RuntimeError('Invalid decoder file bound')
    if command and command[0]=='--sandbox':
        import json
        sandbox=json.loads(command[1]);command=command[2:]
    if not sys.platform.startswith('linux') or not command or command[0] not in ('ffmpeg','ffprobe') or not 1<=cpu_seconds<=14430:
        raise RuntimeError('Invalid internal render invocation')
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(1,signal.SIGKILL,0,0,0)!=0:  # PR_SET_PDEATHSIG
        raise RuntimeError('Cannot enforce render parent lifetime')
    # Covers parent death before prctl; after prctl the kernel enforces it.
    if os.getppid()!=expected_parent:raise SystemExit(1)
    if file_limit is not None:resource.setrlimit(resource.RLIMIT_FSIZE,(file_limit,file_limit))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_NOFILE,(128,128))
    resource.setrlimit(resource.RLIMIT_CPU,(cpu_seconds,cpu_seconds))
    if sandbox is not None:
        import importlib.util
        from pathlib import Path
        spec=importlib.util.spec_from_file_location('render_sandbox',Path(__file__).with_name('render_sandbox.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.apply(sandbox['source'],sandbox['output'],sandbox.get('read_files',()))
    os.execvp(command[0],command)


if __name__=='__main__':main()
