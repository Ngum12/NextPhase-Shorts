"""Prepare a free local Valkey instance; preserves existing private credentials."""
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def private_write(path,text,mode=0o600):
    if path.is_symlink():raise RuntimeError('Queue configuration must be a regular file')
    fd,temporary=tempfile.mkstemp(prefix='queue-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:stream.write(text);stream.flush();os.fsync(stream.fileno())
        if os.name=='posix':os.chmod(temporary,mode)
        os.replace(temporary,path)
    finally:Path(temporary).unlink(missing_ok=True)


def main():
    directory=ROOT/'.data'/'queue-private'
    if (ROOT/'.data').is_symlink() or getattr(ROOT/'.data','is_junction',lambda:False)():raise RuntimeError('Unsafe data folder')
    if directory.is_symlink() or getattr(directory,'is_junction',lambda:False)():raise RuntimeError('Unsafe queue folder')
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name=='posix' and stat.S_IMODE(directory.stat().st_mode)&0o077:raise RuntimeError('Queue folder must be private')
    target=directory/'client.json'
    if target.is_symlink():raise RuntimeError('Queue configuration must be a regular file')
    existing=json.loads(target.read_text()) if target.exists() else {}
    password=existing.get('QUEUE_PASSWORD') or secrets.token_urlsafe(48)
    if len(password)<32 or not all(c.isalnum() or c in '_-' for c in password):raise RuntimeError('Invalid local queue credential')
    settings={'QUEUE_BACKEND':'valkey','QUEUE_HOST':'127.0.0.1','QUEUE_PORT':'6380','QUEUE_PASSWORD':password,'QUEUE_TLS':'false'}
    private_write(target,json.dumps(settings,indent=2)+'\n')
    private_write(directory/'client.env','\n'.join(key+'='+value for key,value in settings.items())+'\n')
    configuration='bind 0.0.0.0\nport 6379\nprotected-mode yes\nrequirepass '+password+'\ndir /data\nappendonly yes\nappendfsync always\nmaxmemory 64mb\nmaxmemory-policy noeviction\nsave ""\n'
    # The containing directory is 0700; readable file supports the unprivileged
    # container UID through a single-file read-only mount, without exposing it on host.
    private_write(directory/'valkey.conf',configuration,0o644)
    print('Prepared private local queue configuration. Credentials were preserved and never printed.')
    print('No broker, paid resource, email or billing was started.')
    if os.name=='nt':print('Keep .data/queue-private protected by current-user NTFS permissions.')


if __name__=='__main__':main()
