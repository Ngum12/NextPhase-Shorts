"""Opt-in private development inbox only. Never contacts SMTP or any provider."""
import json,os,stat,uuid
from .config import get_settings


def write_local_message(action,recipient,token):
    settings=get_settings()
    if settings.auth_mail_backend!='file' or settings.env not in ('development','test'):
        raise RuntimeError('Local email actions are disabled')
    root=settings.auth_mail_dir
    if root.is_symlink() or getattr(root,'is_junction',lambda:False)():raise ValueError('Unsafe local inbox')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name=='posix':
        details=root.stat()
        if details.st_uid!=os.getuid() or stat.S_IMODE(details.st_mode)&0o077:
            raise ValueError('Local inbox must be private to the server user')
    if str(uuid.UUID(action.id))!=action.id:raise ValueError('Invalid mail identity')
    target=root/(action.id+'.json');temporary=root/(action.id+'.tmp')
    payload={'purpose':action.purpose,'recipient':recipient,'code':token,'expires_at':action.expires_at.isoformat(),
             'notice':'Local development only; no outgoing email was sent. Keep this code private.'}
    created=False
    try:
        descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        created=True
        with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
            json.dump(payload,stream);stream.flush();os.fsync(stream.fileno())
        # Never replace a previously published message or an unsafe link.
        if target.exists() or target.is_symlink():raise ValueError('Local mail already exists')
        temporary.rename(target)
        return target
    finally:
        if created:temporary.unlink(missing_ok=True)
