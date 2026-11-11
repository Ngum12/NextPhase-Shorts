"""Linux Landlock file isolation plus seccomp networking/escape denial.

Applied only in a decoder child, never in API/worker control processes. Required
mode fails closed on unsupported kernels; it is not a VM or a kernel-exploit defense.
"""
import ctypes
import errno
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile

READ=1|4|8
WRITE=2|4|8|16|32|128|256|16384
HANDLED=(1<<15)-1  # Landlock ABI 3 filesystem rights, including REFER/TRUNCATE.


class Ruleset(ctypes.Structure):
    _fields_=[('handled_access_fs',ctypes.c_uint64)]


class PathRule(ctypes.Structure):
    _pack_=1
    _fields_=[('allowed_access',ctypes.c_uint64),('parent_fd',ctypes.c_int32)]


class Filter(ctypes.Structure):
    _fields_=[('code',ctypes.c_ushort),('jt',ctypes.c_ubyte),('jf',ctypes.c_ubyte),('k',ctypes.c_uint32)]


class Program(ctypes.Structure):
    _fields_=[('length',ctypes.c_ushort),('filters',ctypes.POINTER(Filter))]


def supported():
    if not sys.platform.startswith('linux') or platform.machine().lower() not in ('x86_64','aarch64','arm64'):return False
    libc=ctypes.CDLL(None,use_errno=True)
    return libc.syscall(444,0,0,1)>=3


def network_filter(libc):
    arch=platform.machine().lower()
    if arch=='x86_64':
        audit=0xC000003E
        denied=[*range(41,56),101,109,112,165,166,250,272,288,298,299,304,307,308,310,311,313,321,323,
            425,426,427,428,429,430,431,432,433,434,438,440,442]
    elif arch in ('aarch64','arm64'):
        audit=0xC00000B7
        denied=[*range(198,213),117,39,40,154,157,219,97,241,242,243,265,268,269,270,271,273,280,282,
            425,426,427,428,429,430,431,432,433,434,438,440,442]
    else:raise RuntimeError('Unsupported sandbox architecture')
    # Check architecture and reject x32 ABI before syscall-number filtering.
    code=[(0x20,0,0,4),(0x15,1,0,audit),(0x06,0,0,0x80000000),(0x20,0,0,0),
        (0x45,0,1,0x40000000),(0x06,0,0,0x00050000|errno.EPERM)]
    for number in denied:
        code.extend([(0x15,0,1,number),(0x06,0,0,0x00050000|errno.EPERM)])
    code.append((0x06,0,0,0x7fff0000))
    filters=(Filter*len(code))(*(Filter(*row) for row in code));program=Program(len(code),filters)
    if libc.prctl(22,2,ctypes.byref(program),0,0)!=0:raise RuntimeError('Cannot restrict decoder system calls')


def caption_read_paths(source, paths):
    """Exact small caption files in the private attempt, never a directory grant."""
    if not isinstance(paths,(list,tuple)) or len(paths)>80:
        raise RuntimeError('Invalid caption file list')
    parent=Path(source).resolve(strict=True).parent
    result=[]
    for name in paths:
        path=Path(name)
        if (path.is_symlink() or path.resolve(strict=True).parent!=parent
                or not path.name.startswith('caption-') or path.suffix!='.txt'
                or not path.is_file() or path.stat().st_size>256):
            raise RuntimeError('Invalid caption read file')
        result.append(path.resolve(strict=True))
    return result


def apply(source,output=None,read_files=()):
    caption_paths=caption_read_paths(source,read_files)
    if not supported():raise RuntimeError('Required decoder isolation is unsupported')
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(38,1,0,0,0)!=0:raise RuntimeError('Cannot enforce no-new-privileges')
    attributes=Ruleset(HANDLED)
    descriptor=libc.syscall(444,ctypes.byref(attributes),ctypes.sizeof(attributes),0)
    if descriptor<0:raise RuntimeError('Cannot create decoder filesystem rules')
    try:
        rules={Path(source).resolve(strict=True):4}
        rules.update({path:4 for path in caption_paths})
        for name in ('/usr','/lib','/lib64','/etc/ld.so.cache','/etc/localtime','/etc/fonts'):
            path=Path(name)
            if path.exists():rules[path.resolve()]=READ if path.is_dir() else 4
        for name in ('/dev/null','/dev/urandom','/dev/random'):
            path=Path(name)
            if path.exists():rules[path]=6 if name=='/dev/null' else 4
        if output is not None:
            target=Path(output).resolve(strict=True)
            if not target.is_file():raise RuntimeError('Decoder output must be one existing private file')
            rules[target]=2|4|16384  # write/read/truncate that file, no directory creation/removal
        for path,access in rules.items():
            fd=os.open(path,os.O_PATH|os.O_CLOEXEC)
            try:
                rule=PathRule(access,fd)
                if libc.syscall(445,descriptor,1,ctypes.byref(rule),0)!=0:
                    raise RuntimeError('Cannot install decoder filesystem rules')
            finally:os.close(fd)
        if libc.syscall(446,descriptor,0)!=0:raise RuntimeError('Cannot restrict decoder filesystem')
    finally:os.close(descriptor)
    network_filter(libc)


def require_support():
    if not supported():raise RuntimeError('Worker requires Linux Landlock ABI >=3 and seccomp')
    with tempfile.TemporaryDirectory(prefix='nextphase-sandbox-probe-') as temporary:
        root=Path(temporary);allowed=root/'allowed';denied=root/'denied'
        allowed.write_text('allowed');denied.write_text('private')
        (root/'output').write_text('')
        try:
            result=subprocess.run([sys.executable,'-I',str(Path(__file__).resolve()),'--probe',str(allowed),str(denied)],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        except (OSError,subprocess.SubprocessError):raise RuntimeError('Decoder isolation probe could not complete') from None
        if result.returncode:raise RuntimeError('Decoder filesystem/network isolation probe failed')


if __name__=='__main__':
    if len(sys.argv)!=4 or sys.argv[1]!='--probe':raise SystemExit(2)
    allowed,denied=Path(sys.argv[2]),Path(sys.argv[3])
    output=allowed.parent/'output'
    apply(allowed,output)
    output.write_text('permitted',encoding='utf-8')
    assert output.read_text(encoding='utf-8')=='permitted'
    try:(allowed.parent/'extra').write_text('denied',encoding='utf-8')
    except PermissionError:pass
    else:raise SystemExit(1)
    assert allowed.read_text(encoding='utf-8')=='allowed'
    try:denied.read_text(encoding='utf-8')
    except PermissionError:pass
    else:raise SystemExit(1)
    try:denied.write_text('overwrite',encoding='utf-8')
    except PermissionError:pass
    else:raise SystemExit(1)
    try:socket.socket()
    except PermissionError:pass
    else:raise SystemExit(1)
