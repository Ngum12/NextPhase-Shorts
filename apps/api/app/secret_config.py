"""Server-only secret file adapter. No values or private paths in errors/reports."""
import os
from pathlib import Path
import stat

NAMES=('JWT_SECRET','DATABASE_URL','S3_ACCESS_KEY_ID','S3_SECRET_ACCESS_KEY',
       'QUEUE_PASSWORD','RESEND_API_KEY','AUTH_MAIL_ENCRYPTION_KEYS')


def read_secret(name,default=''):
    if name not in NAMES:raise ValueError('Unknown secret setting')
    value=os.getenv(name,''); location=os.getenv(name+'_FILE','')
    if not location:return value or default
    if value:raise RuntimeError('Configure either a secret value or its file, never both')
    try:
        path=Path(location)
        # Check the final component and all parents; no symlink/junction indirection.
        if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in (path,*path.parents)):
            raise ValueError()
        descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
        with os.fdopen(descriptor,'rb') as handle:
            metadata=os.fstat(handle.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size>16384:raise ValueError()
            if os.name=='posix' and metadata.st_mode & 0o037:raise ValueError()
            data=handle.read(16385)
        value=data.decode('utf-8').rstrip('\r\n')
        if not value or len(data)>16384 or '\n' in value or '\r' in value or '\x00' in value:raise ValueError()
        return value
    except (OSError,ValueError,UnicodeError):
        raise RuntimeError('Secret file is missing, unsafe or invalid') from None


def sources():
    return {name:('file' if os.getenv(name+'_FILE') else 'environment' if os.getenv(name) else 'unset') for name in NAMES}
