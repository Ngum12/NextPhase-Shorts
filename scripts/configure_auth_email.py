"""Privately prepare local QA configuration. Never enables sending or contacts Resend."""
import getpass
import json
import os
from pathlib import Path
import tempfile
import sys
from cryptography.fernet import Fernet
from email_validator import validate_email,EmailNotValidError

ROOT=Path(__file__).resolve().parents[1]


def main():
    if not sys.stdin.isatty():raise RuntimeError('Run this helper in an interactive terminal; do not pipe API keys')
    root=ROOT/'.data';root.mkdir(exist_ok=True)
    target=root/'auth-email-env.json'
    if root.is_symlink() or getattr(root,'is_junction',lambda:False)() or target.is_symlink():raise RuntimeError('Use a private regular configuration folder')
    previous=json.loads(target.read_text()) if target.exists() else {}
    existing=previous.get('AUTH_MAIL_ENCRYPTION_KEYS','')
    if existing:
        for key in existing.split(','):Fernet(key.strip().encode())
    api_key=getpass.getpass('Resend sending-only API key (hidden; Enter preserves an existing key): ').strip() or previous.get('RESEND_API_KEY','')
    if not 16<=len(api_key)<=512 or any(char.isspace() for char in api_key):raise ValueError('Invalid API key format')
    sender=input('Sender address [noreply@auth.techskillnow.com]: ').strip() or 'noreply@auth.techskillnow.com'
    recipients=input('Your owned QA inbox address (one recipient): ').strip().lower()
    try:
        validate_email(sender,check_deliverability=False);validate_email(recipients,check_deliverability=False)
    except EmailNotValidError:raise ValueError('Enter valid sender and inbox addresses') from None
    settings={'AUTH_MAIL_BACKEND':'resend','AUTH_MAIL_SEND_ENABLED':'false','AUTH_MAIL_FROM':sender,
        'AUTH_MAIL_ENCRYPTION_KEYS':existing or Fernet.generate_key().decode(),'RESEND_API_KEY':api_key,
        'AUTH_MAIL_RECIPIENTS':recipients,'AUTH_MAIL_DAILY_LIMIT':'5','AUTH_MAIL_MONTHLY_LIMIT':'20',
        'AUTH_REQUIRE_VERIFIED_EMAIL':'false'}
    descriptor,path=tempfile.mkstemp(prefix='auth-email-',dir=root)
    try:
        with os.fdopen(descriptor,'w') as stream:
            json.dump(settings,stream,indent=2);stream.flush();os.fsync(stream.fileno())
        os.replace(path,target)
    finally:
        Path(path).unlink(missing_ok=True)
    print('Saved private .data/auth-email-env.json. Sending remains DISABLED. No network request was made.')
    if os.name=='nt':print('Protect this folder with current-user NTFS permissions; file modes do not enforce Windows ACLs.')
    print('Never upload, print or commit this file. Keep a protected backup of its encryption keys.')


if __name__=='__main__':main()
