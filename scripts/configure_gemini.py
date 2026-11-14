"""Enable the private, consent-gated Gemini pilot without displaying credentials.

Run on the VPS checkout, then use the normal backup-first updater. This script
makes no network requests and cannot verify Google project billing settings.
"""
import argparse
import getpass
import os
from pathlib import Path
import re
import stat
import tempfile

ROOT=Path(__file__).resolve().parents[1]
FIELDS={'GEMINI_API_KEY','GEMINI_API_KEY_FILE','GEMINI_PLANNING_ENABLED','GEMINI_FREE_TIER_CONFIRMED'}


def configure(root,key):
    # Google auth keys may contain dots; do not assume a legacy key prefix.
    # Keep the dotenv value bounded and free of whitespace/interpolation syntax.
    if not re.fullmatch(r'[A-Za-z0-9_.-]{16,256}',key):raise ValueError('API key format is invalid')
    directory=Path(root)/'.data'/'vps-trial';target=directory/'server.env'
    if any(p.is_symlink() for p in (target,*target.parents)):
        raise ValueError('Private configuration must not use symbolic links')
    metadata=target.stat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink!=1 or metadata.st_size>65536 or
            metadata.st_uid!=os.getuid() or metadata.st_mode&0o077 or directory.stat().st_mode&0o077):
        raise ValueError('Existing VPS configuration must be private and owned by this user')
    lines=target.read_text().splitlines()
    preserved=[]
    for line in lines:
        name=line.strip().removeprefix('export ').split('=',1)[0].strip()
        if name not in FIELDS:preserved.append(line)
    text='\n'.join(preserved)+f'\nGEMINI_API_KEY={key}\nGEMINI_PLANNING_ENABLED=true\nGEMINI_FREE_TIER_CONFIRMED=true\n'
    descriptor,temporary=tempfile.mkstemp(prefix='.gemini-',dir=directory)
    try:
        with os.fdopen(descriptor,'w') as stream:
            stream.write(text);stream.flush();os.fsync(stream.fileno())
        os.chmod(temporary,0o600);os.replace(temporary,target)
    finally:Path(temporary).unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable',action='store_true',required=True)
    parser.parse_args()
    if os.name!='posix':raise SystemExit('Run this helper in your Linux VPS SSH terminal')
    print('In Google AI Studio, confirm this key belongs to a project with billing disabled.')
    if input('Type FREE to confirm free-tier-only usage: ').strip()!='FREE':
        raise SystemExit('Configuration unchanged')
    key=getpass.getpass('Gemini API key (hidden): ').strip()
    try:configure(ROOT,key)
    except (OSError,ValueError,UnicodeError):raise SystemExit('Configuration refused: check key format and private VPS file ownership/permissions') from None
    print('Private Gemini configuration saved. Key was not displayed. No provider call or service restart was performed.')
    print('Next run: .venv/bin/python scripts/update_private_vps.py --apply')


if __name__=='__main__':main()
