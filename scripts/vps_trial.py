"""Prepare/check a private disposable VPS trial; never provision or migrate data.

Standard library only until the explicit synthetic HTTP exercise. No secret values
or subprocess diagnostics are printed. Docker administrators can inspect runtime
environment credentials; this is not a production secret-manager integration.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'nextphase-vps-trial'
FILES = ('compose.yaml', 'compose.restore-journal.yaml',
         'compose.private-staging.yaml', 'compose.vps-trial.yaml')


def prepare(root=ROOT):
    """Create credentials once; refuse even partially initialized destinations."""
    if os.name != 'posix':
        raise ValueError('Prepare on the Linux VPS, not the working Windows installation')
    data = root / '.data'
    if any(p.is_symlink() for p in (data, *data.parents)):
        raise ValueError('Unsafe data directory')
    data.mkdir(mode=0o700, exist_ok=True)
    if data.stat().st_uid != os.geteuid() or data.stat().st_mode & 0o022:
        raise ValueError('Data directory must be owned by this administrator and not publicly writable')
    destination = data / 'vps-trial'
    destination.mkdir(mode=0o700)  # Exclusive; never rotate a running database password.
    (destination/'asr').mkdir(mode=0o755)
    (destination/'asr').chmod(0o755)
    password = secrets.token_urlsafe(48)
    broker = secrets.token_urlsafe(48)
    url = 'postgresql+psycopg://nextphase:' + password + '@db:5432/nextphase'
    settings = {
        'APP_ENV': 'development', 'JWT_SECRET': secrets.token_urlsafe(48),
        'QUEUE_BACKEND': 'valkey', 'QUEUE_PASSWORD': broker, 'QUEUE_TLS': 'false',
        'MEDIA_BACKEND': 'local', 'DIRECT_UPLOADS_ENABLED': 'false',
        'AUTH_MAIL_BACKEND': 'disabled', 'AUTH_MAIL_SEND_ENABLED': 'false',
        'AUTH_REQUIRE_VERIFIED_EMAIL': 'false', 'AI_PROVIDER': 'disabled',
        'BILLING_PROVIDER': 'disabled', 'GLOBAL_PROCESSING_LIMIT': '1',
        'GLOBAL_ACTIVE_LIMIT': '10', 'INGRESS_LIMIT': '1',
        'API_REQUEST_CONCURRENCY': '4', 'GLOBAL_STORAGE_BYTES': str(20 * 1024**3),
        'MIN_FREE_DISK_BYTES': str(5 * 1024**3),
    }
    contents = {
        'compose.env': 'VPS_DATABASE_URL=' + url + '\nVPS_DB_PASSWORD=' + password + '\n',
        'server.env': ''.join(key + '=' + value + '\n' for key, value in settings.items()),
        'valkey.conf': 'bind 0.0.0.0\nport 6379\nprotected-mode yes\nrequirepass ' + broker
            + '\ndir /data\nappendonly yes\nappendfsync always\nmaxmemory 64mb\n'
            + 'maxmemory-policy noeviction\nsave ""\n',
    }
    for name, content in contents.items():
        # Single-file broker bind must be readable by the image's Valkey UID.
        # Host parent remains 0700; the other files remain 0600.
        mode = 0o644 if name == 'valkey.conf' else 0o600
        fd = os.open(destination / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'w') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    return {'prepared': True, 'credentials_printed': False, 'services_started': False}


def compose_command(root=ROOT):
    directory = root / '.data/vps-trial'
    for path in (directory, *(directory / name for name in ('compose.env', 'server.env', 'valkey.conf'))):
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('Unsafe private configuration')
        mode = path.stat()
        if path == directory:
            if not stat.S_ISDIR(mode.st_mode) or mode.st_mode & 0o077:
                raise ValueError('Private configuration directory required')
        elif not stat.S_ISREG(mode.st_mode) or mode.st_nlink != 1:
            raise ValueError('Regular private configuration files required')
        elif path.name != 'valkey.conf' and mode.st_mode & 0o077:
            raise ValueError('Private credential permissions required')
    return ['docker', '--host=unix:///var/run/docker.sock', 'compose', '--project-name', PROJECT, '--env-file',
            str(directory / 'compose.env'), *[part for file in FILES for part in ('-f', str(root / file))]]


def run(command, root=ROOT, timeout=90):
    # Never inherit Compose profiles, project/file/env overrides or interpolation
    # secrets that could silently select the owner's existing installation.
    selectors = {'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'}
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('COMPOSE_', 'VPS_')) and key not in selectors}
    result = subprocess.run(command, cwd=root, env=env, capture_output=True,
                            text=True, timeout=timeout, check=False)
    if result.returncode:
        raise ValueError('Command failed; inspect the selected private trial with its documented commands')
    return result.stdout


def validate_config(config):
    """Inspect resolved configuration in memory; never print its credentials."""
    services = config['services']
    if config.get('name') != PROJECT:
        raise ValueError('Wrong project')
    allowed = {'api': ('18000', 8000), 'edge': ('18443', 8443)}
    for name, service in services.items():
        if service.get('privileged') or service.get('network_mode') == 'host':
            raise ValueError('Privileged or host-network services forbidden')
        ports = service.get('ports', [])
        for port in ports:
            if (name not in allowed or port.get('host_ip') != '127.0.0.1'
                    or (str(port.get('published')), port.get('target')) != allowed[name]):
                raise ValueError('Unexpected published port')
        if name in allowed and len(ports) != 1:
            raise ValueError('Missing private listener')
    for name in ('api', 'worker', 'migrate', 'queue-supervisor', 'mail-worker'):
        if name == 'mail-worker' and name not in services:
            continue  # Disabled Compose profiles are absent in resolved output.
        env = services[name]['environment']
        if (env.get('APP_ENV') != 'development' or env.get('AUTH_MAIL_SEND_ENABLED') != 'false'
                or env.get('AI_PROVIDER') != 'disabled' or env.get('BILLING_PROVIDER') != 'disabled'
                or env.get('GLOBAL_PROCESSING_LIMIT') != '1'
                or env.get('MEDIA_BACKEND') != 'local'):
            raise ValueError('Unsafe trial settings')
        if ':localdev@' in env['DATABASE_URL'] or len(env.get('JWT_SECRET', '')) < 48:
            raise ValueError('Fresh private credentials required')
    worker = services['worker']
    if (int(worker['mem_limit']) != 2 * 1024**3 or float(worker['cpus']) != 2
            or int(worker['pids_limit']) != 128 or not worker.get('read_only')
            or 'ALL' not in worker.get('cap_drop', [])):
        raise ValueError('Bounded unprivileged worker configuration required')
    if any(worker['environment'].get(key) != 'true'
           for key in ('WORKER_REQUIRE_LIMITS', 'WORKER_REQUIRE_SANDBOX')):
        raise ValueError('Worker protections required')
    if services['operator-agent']['environment'].get('JWT_SECRET'):
        raise ValueError('Observer must not receive API credentials')
    # Explicit project namespaces prevent accidental reuse of PC volumes.
    for volume in config.get('volumes', {}).values():
        if volume.get('external') or not volume.get('name', '').startswith(PROJECT + '_'):
            raise ValueError('Dedicated trial volumes required')
    return {'private_configuration': True, 'render_concurrency': 1,
            'public_release_ready': False}


def accept(root=ROOT, exercise=False):
    command = compose_command(root)
    checks = {}
    failure = None
    try:
        validate_config(json.loads(run(command + ['config', '--format', 'json'], root)))
        checks['private_configuration'] = True
        host = json.loads(run(command + ['exec', '-T', 'worker', 'python', '-m', 'app.worker_hostcheck'], root))
        if host.get('ready') is not True:
            raise ValueError('Worker containment unavailable')
        checks['worker_containment'] = True
        run(command + ['exec', '-T', 'operator-agent', 'python', '-m', 'app.staging_check'], root)
        checks['verified_private_https'] = True
        run(command + ['exec', '-T', 'worker', 'python', '-m', 'app.monitoring', '--check'], root)
        checks['monitoring'] = True
        run(command + ['exec', '-T', 'operator-agent', 'python', '-m', 'app.operator_agent',
                       '--once', '--url', 'https://edge:9443', '--ca-file',
                       '/var/nextphase/staging-agent/root.crt'], root)
        checks['operator_receipt'] = True
        if exercise:
            if sys.flags.optimize:
                raise ValueError('Synthetic smoke requires Python assertions enabled')
            run([sys.executable, str(root / 'scripts/smoke_e2e.py'),
                 '--base-url', 'http://127.0.0.1:18000'], root, timeout=900)
            checks['synthetic_upload_render_download'] = True
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError):
        failure = 'trial_check_failed'
    report = {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
              'checks': checks, 'failure': failure, 'synthetic_exercise_requested': exercise,
              'workflow_tested': checks.get('synthetic_upload_render_download', False),
              'trial_checks_passed': failure is None,
              'public_release_ready': False,
              'scope': 'private disposable trial; not migration, public HTTPS, offsite recovery or production acceptance'}
    directory = root / '.data/vps-trial'
    path = directory / ('acceptance-' + uuid.uuid4().hex + '.json')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'check', 'accept'))
    parser.add_argument('--synthetic', action='store_true',
                        help='Create disposable test accounts/jobs on the isolated trial')
    args = parser.parse_args()
    try:
        if args.action == 'prepare':
            result = prepare()
        elif args.action == 'check':
            command = compose_command()
            result = validate_config(json.loads(run(command + ['config', '--format', 'json'])))
        else:
            result = accept(exercise=args.synthetic)
        print(json.dumps(result, indent=2))
        if result.get('failure'):
            raise SystemExit(1)
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError):
        parser.exit(1, 'VPS trial refused; check private prerequisites. No credential values printed.\n')


if __name__ == '__main__':
    main()
