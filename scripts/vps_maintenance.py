"""Private VPS trial maintenance. No provisioning, live restore or automatic deletion.

Nightly backups pause writers, authenticate a readback and publish a user-readable
encrypted copy. Monitoring sends only coarse status to an explicitly configured
recipient. Offsite copies require explicit setup and a successful remote readback.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import getpass
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import signal
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

from vps_trial import ROOT, compose_command

WRITERS = ('api', 'worker', 'queue-supervisor', 'mail-worker', 'operator-agent')
DOMAIN = 'shorts-api.techskillnow.com'
GIB = 1024 ** 3
BUSY_CODE = ('from sqlalchemy import select,func;from app.db import SessionLocal;'
             'from app.models import RenderJob;'
             'db=SessionLocal();print(db.scalar(select(func.count()).select_from(RenderJob)'
             '.where(RenderJob.status.in_(["queued","processing"]))));db.close()')

BACKUP_CODE = r'''
import hashlib,json,shutil,sys
from pathlib import Path
from app.backup_bundle import create,restore
from app.restore_journal import configured
from app.restore_replay import expected_checkpoint
stamp=sys.argv[1]
bundle=Path('/backups')/(stamp+'.npb')
verify=Path('/backups')/('verify-'+stamp)
key='/var/nextphase/staging-offline/backup.key'
create(bundle,database_dump=Path('/input')/stamp/'database.dump',media='/source/media',
       journal=configured(),checkpoint=expected_checkpoint(Path('/input')/stamp/'checkpoint.json'),
       key_file=key,offline=True)
result=restore(bundle,verify,key)
if result.get('authenticated') is not True:raise RuntimeError('Readback failed')
shutil.rmtree(verify)  # Only this run's exclusively created authenticated copy.
with bundle.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
print(json.dumps({'authenticated':True,'sha256':digest}))
'''


def private_dir(path):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise RuntimeError('Unsafe maintenance directory')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError('Private administrator-owned directory required')
    return path


def state_dir():
    return private_dir(ROOT / '.data/maintenance')


def save(name, value):
    path = state_dir() / name
    if path.is_symlink():
        raise RuntimeError('Unsafe status file')
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex)
    with tmp.open('x') as out:
        os.chmod(tmp, 0o600)
        json.dump(value, out)
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, path)


def read(name):
    path = state_dir() / name
    if not path.exists():
        return {}
    if path.is_symlink():
        raise RuntimeError('Unsafe status file')
    return json.loads(path.read_text())


def command(args, *, output=None, timeout=300):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('COMPOSE_', 'VPS_')) and k not in
           ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH')}
    if output:
        with Path(output).open('xb') as out:
            os.chmod(output, 0o600)
            result = subprocess.run(args, cwd=ROOT, env=env, stdout=out,
                                    stderr=subprocess.PIPE, timeout=timeout)
    else:
        result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True,
                                text=True, timeout=timeout)
    if result.returncode:
        # Never echo environment values, database dumps or raw mail responses.
        raise RuntimeError('Maintenance command failed')
    return result.stdout if not output else ''


def dc(*args, **kwargs):
    return command(compose_command() + list(args), **kwargs)


def running_writers():
    running = set(dc('ps', '--status', 'running', '--services').split())
    if not {'api', 'worker', 'queue-supervisor', 'db', 'queue'} <= running:
        raise RuntimeError('Required trial services are not running')
    return [s for s in WRITERS if s in running]


def backup():
    root = state_dir()
    with (root / 'backup.lock').open('a') as lock:
        os.chmod(root / 'backup.lock', 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another backup is running') from None
        return backup_locked()


def backup_locked():
    # A reserve is an early guard; the archive implementation also checks space.
    if shutil.disk_usage(ROOT).free < 10 * GIB:
        raise RuntimeError('Backup requires at least 10 GiB free')
    stamp = 'scheduled-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    inputs = ROOT / '.data/staging-input'
    outputs = ROOT / '.data/encrypted-backups'
    for p in (inputs, outputs):
        if any(x.is_symlink() for x in (p, *p.parents)):
            raise RuntimeError('Unsafe backup directory')
        p.mkdir(mode=0o700, exist_ok=True)
    work = inputs / stamp
    work.mkdir(mode=0o700)
    destination = private_dir(ROOT / '.data/scheduled-backups') / (stamp + '.npb')
    identity = json.loads(dc('run', '--rm', '--no-deps', '-T', 'backup-tool', '-c',
        'import os,json;print(json.dumps({"uid":os.getuid()}))'))['uid']
    # Bind mounts preserve host IDs: administrator UID 1001 != app UID 1000.
    for path, rights in ((inputs, 'rx'), (work, 'rx'), (outputs, 'rwx')):
        command(['setfacl', '-m', f'u:{identity}:{rights}', str(path)])
    writers = running_writers()
    if int(dc('exec', '-T', 'api', 'python', '-c', BUSY_CODE).strip()) != 0:
        raise RuntimeError('Queued or processing renders; backup deferred')
    media_bytes = int(dc('exec', '-T', 'worker', 'python', '-c',
        'from pathlib import Path;print(sum(p.stat().st_size for p in '
        'Path("/var/nextphase/media").rglob("*") if p.is_file()))').strip())
    db_bytes = int(dc('exec', '-T', 'db', 'psql', '-U', 'nextphase', '-d', 'nextphase',
                      '-At', '-c', 'SELECT pg_database_size(current_database());').strip())
    if shutil.disk_usage(ROOT).free < 10 * GIB + 4 * (media_bytes + db_bytes):
        raise RuntimeError('Insufficient space for backup and authenticated readback reserve')
    name = 'nextphase-backup-' + uuid.uuid4().hex
    paused = False
    container_started = False
    verified = False
    try:
        save('paused-writers.json', {'paused': True, 'writers': writers, 'stamp': stamp})
        paused = True  # Even a partially failed stop requires a restart attempt.
        dc('stop', *writers)
        busy = dc('run', '--rm', '--no-deps', '-T', 'api', 'python', '-c', BUSY_CODE)
        if int(busy.strip()) != 0:
            raise RuntimeError('Queued or processing renders; backup deferred')
        dc('exec', '-T', 'db', 'pg_dump', '-U', 'nextphase', '-d', 'nextphase', '-Fc',
           output=work / 'database.dump', timeout=900)
        dc('run', '--rm', '--no-deps', '-T', 'backup-tool', '-m', 'app.restore_replay', '--checkpoint',
           output=work / 'checkpoint.json')
        for path in work.iterdir():
            command(['setfacl', '-m', f'u:{identity}:r', str(path)])
        container_started = True
        result = json.loads(dc('run', '--name', name, '--no-deps', '-T', 'backup-tool',
                               '-c', BACKUP_CODE, stamp, timeout=1800))
        if result.get('authenticated') is not True:
            raise RuntimeError('Backup readback not authenticated')
        command(['docker', '--host=unix:///var/run/docker.sock', 'cp',
                 name + ':/backups/' + stamp + '.npb', str(destination)])
        os.chmod(destination, 0o600)
        with destination.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if digest != result.get('sha256'):
            raise RuntimeError('Backup transfer hash mismatch')
        verified = True
    finally:
        # Resume only the services observed running; never activate real mail.
        try:
            if paused:
                dc('up', '-d', '--no-deps', '--no-recreate', '--no-build', '--pull', 'never',
                   '--wait', '--wait-timeout', '120', *writers)
                save('paused-writers.json', {'paused': False})
        finally:
            if container_started:
                command(['docker', '--host=unix:///var/run/docker.sock', 'rm', name])
    if not verified:
        raise RuntimeError('Backup verification incomplete')
    result = {'ok': True, 'completed_at': time.time(), 'file': destination.name,
              'sha256': digest, 'authenticated_readback': True, 'offsite_copy': False}
    save('backup-latest.json', result)
    # Inputs are this run's new files only. Retain failed inputs for diagnosis.
    shutil.rmtree(work)
    # Preserve original ciphertext too; no automatic backup retention/deletion.
    return result


def certificate_days():
    with socket.create_connection(('127.0.0.1', 443), timeout=10) as raw:
        with ssl.create_default_context().wrap_socket(raw, server_hostname=DOMAIN) as tls:
            expiry = ssl.cert_time_to_seconds(tls.getpeercert()['notAfter'])
    return (expiry - time.time()) / 86400


def resume():
    with (state_dir() / 'backup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = read('paused-writers.json')
        if state.get('paused'):
            writers = state.get('writers', [])
            if not writers or not set(writers) <= set(WRITERS):
                raise RuntimeError('Invalid saved writer selection')
            dc('up', '-d', '--no-deps', '--no-recreate', '--no-build', '--pull', 'never',
               '--wait', '--wait-timeout', '120', *writers)
            save('paused-writers.json', {'paused': False})
    return {'ok': True, 'writers_resumed_if_needed': True}


def offsite_upload(settings=None):
    """Copy one verified encrypted bundle only; never sync/delete a Drive folder."""
    settings = settings or read('offsite.json')
    remote = settings.get('remote', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]+:[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', remote):
        raise RuntimeError('Invalid dedicated backup remote')
    config = Path(settings['config_file'])
    if (not config.is_absolute() or any(p.is_symlink() for p in (config, *config.parents))
            or config.stat().st_uid != os.getuid() or config.stat().st_mode & 0o077
            or not config.is_file()):
        raise RuntimeError('Private administrator-owned rclone configuration required')
    with (state_dir()/'offsite.lock').open('a') as lock:
        os.chmod(state_dir()/'offsite.lock', 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        latest = read('backup-latest.json')
        name = latest.get('file', '')
        if not latest.get('authenticated_readback') or not re.fullmatch(
                r'scheduled-\d{8}T\d{6}Z-[0-9a-f]{8}\.npb', name):
            raise RuntimeError('No verified scheduled backup selected')
        source = ROOT/'.data/scheduled-backups'/name
        if source.is_symlink() or not source.is_file():
            raise RuntimeError('Encrypted backup missing')
        with source.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        if digest != latest.get('sha256'):
            raise RuntimeError('Local backup hash changed; upload refused')
        base = ['rclone', '--config', str(config)]
        command(base+['copyto', str(source), remote+'/'+name, '--immutable', '--checksum',
                      '--retries', '3', '--low-level-retries', '3', '--contimeout', '20s',
                      '--timeout', '60s', '--log-level', 'ERROR'], timeout=1800)
        command(base+['check', str(source.parent), remote, '--include', name,
                      '--one-way', '--download', '--contimeout', '20s', '--timeout', '60s',
                      '--log-level', 'ERROR'], timeout=1800)
        # Do not mark a newer concurrent backup as uploaded based on an older file.
        current = read('backup-latest.json')
        if current.get('file') == name and current.get('sha256') == digest:
            save('backup-latest.json', {**current, 'offsite_copy': True})
        result = {'ok': True, 'verified_at': time.time(), 'file': name,
                  'sha256': digest, 'offsite_copy': True, 'download_verified': True}
        save('offsite-latest.json', result)
        return result


def offsite_setup():
    if read('offsite.json'):
        raise RuntimeError('Existing offsite settings preserved; use offsite to retry')
    config = Path.home()/'.config/rclone/rclone.conf'
    remotes = command(['rclone', '--config', str(config), 'listremotes']).split()
    if 'nextphase-backups:' not in remotes:
        raise RuntimeError('Expected configured backup remote not found')
    settings = {'remote': 'nextphase-backups:NextPhase-Automated-Backups',
                'config_file': str(config)}
    result = offsite_upload(settings)
    # Activate only after actual ciphertext upload and full remote readback pass.
    save('offsite.json', {**settings, 'enabled': True, 'enabled_at': time.time()})
    return {**result, 'automatic_uploads_enabled': True}


def monitoring():
    issues = []
    free = shutil.disk_usage(ROOT).free
    if free < 5 * GIB:
        issues.append('disk_below_5_gib')
    try:
        days = certificate_days()
        if days < 14:
            issues.append('certificate_under_14_days')
    except Exception:
        days = None
        issues.append('verified_https_unavailable')
    latest = read('backup-latest.json')
    if time.time() - latest.get('completed_at', 0) > 30 * 3600:
        issues.append('backup_missing_or_older_than_30_hours')
    if read('backup-failure.json').get('checked_at', 0) > latest.get('completed_at', 0):
        issues.append('last_backup_attempt_failed')
    if read('offsite.json').get('enabled'):
        cloud = read('offsite-latest.json')
        if time.time()-cloud.get('verified_at', 0) > 30*3600:
            issues.append('offsite_copy_missing_or_older_than_30_hours')
        if read('offsite-failure.json').get('checked_at', 0) > cloud.get('verified_at', 0):
            issues.append('last_offsite_copy_failed')
        if not latest.get('offsite_copy') and time.time()-latest.get('completed_at', 0) > 2*3600:
            issues.append('latest_backup_not_offsite_after_two_hours')
    with (state_dir() / 'backup.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            maintenance = False
        except BlockingIOError:
            maintenance = True
        if not maintenance:
            if read('paused-writers.json').get('paused'):
                issues.append('writers_need_resume')
            try:
                client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with client.open('http://127.0.0.1:18000/ready', timeout=10) as response:
                    if json.load(response) != {'ok': True, 'service': 'nextphase-shorts'}:
                        raise RuntimeError()
            except Exception:
                issues.append('api_readiness_failed')
            try:
                dc('exec', '-T', 'worker', 'python', '-m', 'app.monitoring', '--check', timeout=60)
            except Exception:
                issues.append('worker_or_queue_monitor_failed')
    result = {'ok': not issues, 'checked_at': time.time(), 'issues': issues,
              'maintenance': maintenance, 'free_gib': round(free/GIB, 1),
              'certificate_days': round(days, 1) if days is not None else None}
    save('monitor-latest.json', result)
    return result


def notify(result, *, test=False, topic='monitor'):
    config = state_dir() / 'email.json'
    if not config.exists():
        return 'not_configured'
    if config.is_symlink() or config.stat().st_mode & 0o077:
        raise RuntimeError('Email settings must be private')
    settings = json.loads(config.read_text())
    keyfile = state_dir() / 'resend.key'
    if keyfile.is_symlink() or keyfile.stat().st_mode & 0o077:
        raise RuntimeError('Email key file must be private')
    key = keyfile.read_text().strip()
    if not key or '\n' in key or '\r' in key:
        raise RuntimeError('Invalid mail binding')
    failed = not result.get('ok', False)
    previous = read('email-last-'+topic+'.json')
    fingerprint = json.dumps({'failed': failed, 'issues': result.get('issues', [])}, sort_keys=True)
    if not test and (not failed and not previous.get('failed') or
                     previous.get('fingerprint') == fingerprint and time.time()-previous.get('sent_at', 0)<3600):
        return 'unchanged_or_throttled'
    payload = {'from': settings['from'], 'to': [settings['to']],
               'subject': 'NextPhase VPS '+topic+': ' + ('email test' if test else 'attention needed' if failed else 'recovered'),
               'text': ('NextPhase VPS maintenance test.' if test else
                        'Status: ' + ('attention required' if failed else 'recovered') + '\n' +
                        '\n'.join(result.get('issues', []))) +
                       '\nCheck the private server maintenance status. No customer data is included.'}
    request = urllib.request.Request('https://api.resend.com/emails',
        data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer '+key,
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'User-Agent': 'NextPhase-VPS-Maintenance/1.0'}, method='POST')
    with urllib.request.urlopen(request, timeout=20) as response:
        receipt = json.load(response)
        if not receipt.get('id'):
            raise RuntimeError('Email provider did not acknowledge acceptance')
    save('email-last-'+topic+'.json', {'sent_at': time.time(), 'failed': failed, 'fingerprint': fingerprint})
    return 'provider_accepted_not_inbox_verified'


def email_error(error):
    """Expose fixed classifications, never raw bodies, headers or credentials."""
    result = {'issue': 'email_delivery_failed'}
    if isinstance(error, urllib.error.HTTPError):
        result['http_status'] = error.code
        body = error.read(8192)
        try:
            name = json.loads(body).get('name')
            allowed = {'validation_error', 'missing_api_key', 'invalid_api_key',
                       'restricted_api_key', 'rate_limit_exceeded', 'application_error',
                       'not_found', 'security_error'}
            result['provider_error'] = name if name in allowed else 'unclassified'
            result['response_format'] = 'json'
        except (ValueError, AttributeError, TypeError):
            result['response_format'] = 'non_json'
            result['edge_filter_marker'] = b'cloudflare' in body.lower() or b'error code: 1010' in body.lower()
    elif isinstance(error, urllib.error.URLError):
        result['issue'] = 'email_connection_failed'
    return result


def units():
    user = pwd.getpwuid(os.getuid()).pw_name
    if user == 'root' or any(c.isspace() for c in str(ROOT)):
        raise RuntimeError('Generate units as the normal VPS administrator in an unspaced checkout path')
    directory = private_dir(state_dir() / 'systemd')
    for action, schedule in [('backup', '*-*-* 02:00:00 UTC'), ('monitor', '*-*-* *:0/5:00 UTC')]:
        service = f'''[Unit]
Description=NextPhase private trial {action}
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User={user}
WorkingDirectory={ROOT}
UMask=0077
ExecStart={sys.executable} {ROOT}/scripts/vps_maintenance.py {action}
TimeoutStartSec={'45min' if action=='backup' else '3min'}
TimeoutStopSec=3min
{('ExecStopPost='+sys.executable+' '+str(ROOT)+'/scripts/vps_maintenance.py resume') if action=='backup' else ''}
'''
        timer = f'''[Unit]
Description=NextPhase {action} schedule

[Timer]
OnCalendar={schedule}
Persistent=true
Unit=nextphase-{action}.service

[Install]
WantedBy=timers.target
'''
        for suffix, content in [('service', service), ('timer', timer)]:
            path = directory / f'nextphase-{action}.{suffix}'
            if path.exists():
                raise RuntimeError('Existing generated units preserved; review before regenerating')
            path.write_text(content)
    return {'ok': True, 'generated': str(directory), 'installed': False,
            'backup_time': '04:00 Africa/Kigali', 'monitor_interval_minutes': 5}


def email_setup(sender, recipient):
    from email_validator import validate_email
    sender = validate_email(sender, check_deliverability=False).normalized
    recipient = validate_email(recipient, check_deliverability=False).normalized
    directory = state_dir()
    if any((directory/name).exists() for name in ('email.json', 'resend.key')):
        raise RuntimeError('Existing mail configuration preserved')
    if not sys.stdin.isatty():
        raise RuntimeError('Use an interactive terminal for the hidden key prompt')
    key = getpass.getpass('Resend sending API key (hidden; never paste in chat): ').strip()
    if not key or any(c.isspace() for c in key):
        raise RuntimeError('Invalid mail key')
    for name, content in [('resend.key', key), ('email.json', json.dumps({'from': sender, 'to': recipient}))]:
        with (directory/name).open('x') as out:
            os.chmod(directory/name, 0o600)
            out.write(content)
    return {'ok': True, 'mail_configured': True, 'email_sent': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('backup', 'monitor', 'units', 'status', 'email-test', 'email-setup', 'resume', 'offsite-setup', 'offsite'))
    parser.add_argument('--sender', help='Verified Resend sender address; no API keys in arguments')
    parser.add_argument('--recipient', help='Explicit operator failure-alert recipient')
    args = parser.parse_args()
    os.umask(0o077)
    def interrupt(signum, frame):
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        raise RuntimeError('Maintenance interrupted')
    signal.signal(signal.SIGTERM, interrupt)
    try:
        if args.action == 'offsite-setup':
            result = offsite_setup()
        elif args.action == 'email-setup':
            result = email_setup(args.sender, args.recipient)
        elif args.action == 'resume':
            result = resume()
        elif args.action == 'units':
            result = units()
        elif args.action == 'status':
            result = {'backup': read('backup-latest.json'), 'monitor': read('monitor-latest.json'),
                      'backup_failure': read('backup-failure.json'),
                      'email_failure': read('email-failure.json'),
                      'offsite': read('offsite-latest.json'),
                      'offsite_enabled': read('offsite.json').get('enabled', False),
                      'offsite_failure': read('offsite-failure.json'),
                      'paused_writers': read('paused-writers.json')}
        elif args.action == 'email-test':
            result = {'ok': True, 'email': notify({'ok': True}, test=True)}
        else:
            try:
                if args.action == 'backup':
                    result = backup()
                elif args.action == 'offsite':
                    result = offsite_upload()
                else:
                    result = monitoring()
            except Exception:
                result = {'ok': False, 'issues': [args.action+'_failed'], 'checked_at': time.time()}
                save(args.action+'-failure.json', result)
            if args.action == 'backup' and result.get('ok') and read('offsite.json').get('enabled'):
                try:
                    upload = offsite_upload()
                    result['offsite_copy'] = upload['offsite_copy']
                    result['download_verified'] = upload['download_verified']
                except Exception:
                    result.update(ok=False, issues=['offsite_copy_failed'])
                    save('offsite-failure.json', {'checked_at': time.time(), 'issue': 'offsite_copy_failed'})
            try:
                result['email'] = notify(result, topic=args.action)
            except Exception as error:
                result['email'] = 'delivery_failed'
                result['email_error'] = email_error(error)
                result['ok'] = False
                save('email-failure.json', {'checked_at': time.time(), **result['email_error']})
        print(json.dumps(result))
        return 0 if result.get('ok', True) else 1
    except Exception as error:
        details = email_error(error) if args.action == 'email-test' else {'issue': 'maintenance_refused_no_credentials_printed'}
        print(json.dumps({'ok': False, **details}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
