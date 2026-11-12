"""Private worker ASR launcher with the same required filesystem/network gate."""
import ctypes
import json
import os
from pathlib import Path
import resource
import signal
import sys


def main():
    parent=int(sys.argv[1]);seconds=int(sys.argv[2]);policy=json.loads(sys.argv[3]);command=sys.argv[4:]
    if not 1<=seconds<=1830 or not command or not os.path.isabs(command[0]):raise RuntimeError('Invalid ASR invocation')
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(1,signal.SIGKILL,0,0,0)!=0 or os.getppid()!=parent:raise RuntimeError('ASR parent lifetime unavailable')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_NOFILE,(128,128))
    resource.setrlimit(resource.RLIMIT_CPU,(seconds,seconds))
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
    if policy['required']:
        import importlib.util
        spec=importlib.util.spec_from_file_location('sandbox',Path(__file__).with_name('render_sandbox.py'))
        sandbox=importlib.util.module_from_spec(spec);spec.loader.exec_module(sandbox)
        audio=Path(policy['audio']).resolve(strict=True);model=Path(policy['model']).resolve(strict=True)
        output=Path(policy['output']).resolve(strict=True);engine=Path(command[0]).resolve(strict=True)
        if not audio.parent==output.parent or not all(p.is_file() for p in (audio,model,output,engine)):
            raise RuntimeError('Invalid ASR file scope')
        if (model!=Path('/opt/nextphase-asr-model/ggml-base.bin')
                or engine!=Path('/opt/nextphase-asr/whisper-cli')
                or model.stat().st_mode & 0o222 or engine.stat().st_mode & 0o022):
            raise RuntimeError('ASR requires fixed read-only trusted artifacts')
        if model.stat().st_size>160*1024**2:raise RuntimeError('ASR model exceeds bound')
        sandbox.apply_files(audio,output,{model:4,engine:1|4})
    os.execve(command[0],command,dict(os.environ))


if __name__=='__main__':main()
