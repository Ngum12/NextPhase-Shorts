"""Create-only local Docker journal setup. Never repairs/replaces an existing stream."""
import os
from pathlib import Path
import pwd
from cryptography.fernet import Fernet


def main():
    root=Path('/var/nextphase/restore')
    try:
        empty=os.geteuid()==0 and not root.is_symlink() and root.is_dir() and not any(root.iterdir())
    except OSError:empty=False
    if not empty:
        raise SystemExit('Journal setup refused: requires an empty dedicated volume and the one-off init service.')
    account=pwd.getpwnam('nextphase')
    root.chmod(0o700);os.chown(root,account.pw_uid,account.pw_gid)
    os.setgroups([]);os.setgid(account.pw_gid);os.setuid(account.pw_uid)
    key_file=root/'journal.key'
    descriptor=os.open(key_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    key=Fernet.generate_key()
    with os.fdopen(descriptor,'wb') as handle:
        handle.write(key);handle.flush();os.fsync(handle.fileno())
    descriptor=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)
    from .restore_journal import Journal
    Journal(root/'events',key.decode()).initialize()
    print('Independent local journal initialized. No key value was printed. Keep volume and key out of DB/media rollback.')


if __name__=='__main__':main()
