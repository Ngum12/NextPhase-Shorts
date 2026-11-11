"""Linux local-pilot ASR launcher; isolated from server/provider credentials.

Applies process-lifetime/CPU/address-space/file limits. This does not implement
the production worker's filesystem/network sandbox and is not a tenant boundary.
"""
import ctypes
import os
import resource
import signal
import sys


def main():
    parent=int(sys.argv[1]);cpu=int(sys.argv[2]);command=sys.argv[3:]
    if not sys.platform.startswith('linux') or not 1<=cpu<=3630 or not command or not os.path.isabs(command[0]):
        raise RuntimeError('Invalid local analysis invocation')
    if ctypes.CDLL(None,use_errno=True).prctl(1,signal.SIGKILL,0,0,0)!=0 or os.getppid()!=parent:
        raise RuntimeError('Cannot enforce analysis parent lifetime')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
    resource.setrlimit(resource.RLIMIT_CPU,(cpu,cpu))
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
    os.execve(command[0],command,dict(os.environ))


if __name__=='__main__':main()
