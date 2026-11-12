"""Stage the previously downloaded public base model; no downloads or secrets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

ROOT=Path(__file__).resolve().parents[1]
BASE_SHA1='465707469ff3a37a2b9b8d8f89f2f99de7299dac'


def prepare(root=ROOT,enable=False):
    trial=root/'.data/vps-trial';folder=trial/'asr'
    if any(p.is_symlink() for p in (folder,*folder.parents)):raise RuntimeError('Unsafe model directory')
    folder.mkdir(mode=0o755,exist_ok=True);folder.chmod(0o755)
    if not enable:return {'enabled':False}
    source=root/'.data/asr-pilot/ggml-base.bin';target=folder/'ggml-base.bin'
    if any(p.is_symlink() for p in (source,*source.parents)) or not source.is_file() or not 0<source.stat().st_size<=160*1024**2:
        raise RuntimeError('Previously verified multilingual base model is required')
    with source.open('rb') as handle:
        if hashlib.file_digest(handle,'sha1').hexdigest()!=BASE_SHA1:raise RuntimeError('Pinned base-model identity differs')
    with source.open('rb') as handle:digest=hashlib.file_digest(handle,'sha256').hexdigest()
    if target.exists():
        if target.is_symlink():raise RuntimeError('Unsafe existing model')
        with target.open('rb') as handle:
            if hashlib.file_digest(handle,'sha256').hexdigest()!=digest:raise RuntimeError('Existing model preserved; live rotation refused')
    else:
        fd,name=tempfile.mkstemp(prefix='model-',dir=folder)
        try:
            with os.fdopen(fd,'wb') as output,source.open('rb') as original:shutil.copyfileobj(original,output)
            with Path(name).open('rb') as handle:
                if hashlib.file_digest(handle,'sha256').hexdigest()!=digest:raise RuntimeError('Model changed during staging')
            os.chmod(name,0o444);os.replace(name,target)
        finally:Path(name).unlink(missing_ok=True)
    target.chmod(0o444)
    env=trial/'server.env'
    if env.is_symlink() or env.stat().st_uid!=os.getuid() or env.stat().st_mode & 0o077:raise RuntimeError('Private server settings required')
    lines=env.read_text().splitlines()
    if 'ENGLISH_REVIEW_ENABLED=true' not in lines:raise RuntimeError('Enable the existing private English review first')
    names=('ENGLISH_ANALYSIS_ENABLED','ENGLISH_ANALYSIS_MODEL_SHA256')
    lines=[line for line in lines if not any(line.startswith(name+'=') for name in names)]
    fd,name=tempfile.mkstemp(prefix='server-',dir=trial)
    try:
        with os.fdopen(fd,'w') as handle:handle.write('\n'.join(lines+['ENGLISH_ANALYSIS_ENABLED=true','ENGLISH_ANALYSIS_MODEL_SHA256='+digest])+'\n')
        os.chmod(name,0o600);os.replace(name,env)
    finally:Path(name).unlink(missing_ok=True)
    return {'enabled':True,'model_sha256':digest,'downloaded':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--enable',action='store_true');args=parser.parse_args()
    try:print(json.dumps({'ok':True,**prepare(enable=args.enable)}))
    except Exception as error:
        print(json.dumps({'ok':False,'issue':'model_preparation_refused','error_type':type(error).__name__}));raise SystemExit(1)
