"""Linux exec launcher: no server credentials, parent-death kill and OS limits.

Only the server's fixed FFmpeg/FFprobe invocations use this internal module. This is
defense in depth, not a security sandbox against a compromised decoder.
"""
import ctypes
import os
import signal
import sys


def main():
    import resource
    expected_parent=int(sys.argv[1]);cpu_seconds=int(sys.argv[2]);command=sys.argv[3:]
    if not sys.platform.startswith('linux') or not command or command[0] not in ('ffmpeg','ffprobe') or not 1<=cpu_seconds<=14430:
        raise RuntimeError('Invalid internal render invocation')
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(1,signal.SIGKILL,0,0,0)!=0:  # PR_SET_PDEATHSIG
        raise RuntimeError('Cannot enforce render parent lifetime')
    # Covers parent death before prctl; after prctl the kernel enforces it.
    if os.getppid()!=expected_parent:raise SystemExit(1)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_NOFILE,(128,128))
    resource.setrlimit(resource.RLIMIT_CPU,(cpu_seconds,cpu_seconds))
    os.execvp(command[0],command)


if __name__=='__main__':main()
