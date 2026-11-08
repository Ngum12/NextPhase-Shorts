"""Disposable, loopback-only real S3 smoke. Docker and project venv required.

Creates only a local container with generated test credentials. No cloud accounts,
paid resources, real footage or existing application volumes are used.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'chrislusf/seaweedfs:4.06@sha256:a064c6923daf4451c943cec2f437a67523d7792ee589089bc4d4c27a61d78dea'


def start_store(run, name, config):
    # Do not bind-mount a host-UID-owned 0600 secret. The image drops to UID
    # 1000, while GitHub runners can use UID 1001. Docker cp installs the private
    # file before startup; the official entrypoint chowns /data to seaweed.
    run('create', '--name', name, '-p', '127.0.0.1::8333', IMAGE,
        'server', '-dir=/data', '-ip=127.0.0.1', '-master.volumeSizeLimitMB=64',
        '-volume.max=16', '-s3', '-s3.ip.bind=0.0.0.0',
        '-s3.config=/data/s3.json', stdout=subprocess.DEVNULL, timeout=180)
    run('cp', str(config), name+':/data/s3.json', timeout=15)
    run('start', name, stdout=subprocess.DEVNULL, timeout=30)


def safe_error(error):
    # Raw SDK errors can contain URLs; only expose the exception type and the
    # standard service error code, never request parameters or credentials.
    import re
    response = getattr(error, 'response', None)
    details = response.get('Error') if isinstance(response, dict) else None
    code = str(details.get('Code', '')) if isinstance(details, dict) else ''
    code = code if re.fullmatch(r'[A-Za-z0-9_]{1,64}', code) else ''
    return type(error).__name__ + (':'+code if code else '')


def sanitized_log(text, access, secret):
    import re
    text = text.replace(access, '[REDACTED]').replace(secret, '[REDACTED]')
    return re.sub(r'(?i)([?&]X-Amz-[^=\s]+)=([^&\s]+)', r'\1=[REDACTED]', text)


def main():
    name = 'nextphase-s3-smoke-' + uuid.uuid4().hex[:12]
    directory = ROOT/'.data'/name
    directory.mkdir(parents=True, mode=0o700)
    config = directory/'s3.json'
    access, secret = secrets.token_hex(16), secrets.token_hex(32)
    config.write_text(json.dumps({'identities':[{'name':'local-smoke-only',
        'credentials':[{'accessKey':access,'secretKey':secret}],
        'actions':['Admin','Read','Write','List','Tagging']}]}))
    config.chmod(0o600)
    # Preserve registry credentials/proxies but select only the local daemon.
    docker_env = {**os.environ, **dict.fromkeys(['JWT_SECRET_FILE', 'DATABASE_URL_FILE', 'S3_ACCESS_KEY_ID_FILE', 'S3_SECRET_ACCESS_KEY_FILE', 'QUEUE_PASSWORD_FILE', 'RESEND_API_KEY_FILE', 'AUTH_MAIL_ENCRYPTION_KEYS_FILE'], '')}
    for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):
        docker_env.pop(key, None)
    docker = ['docker','--host=unix:///var/run/docker.sock'] if os.name != 'nt' else ['docker','--context','default']
    def run(*args, **kwargs):
        return subprocess.run(docker+list(args),env=docker_env,check=True,**kwargs)
    try:
        start_store(run, name, config)
        port = run('port',name,'8333/tcp',capture_output=True,text=True,timeout=10).stdout.strip().rsplit(':',1)[1]
        endpoint = f'http://127.0.0.1:{port}'
        env = {**os.environ, **dict.fromkeys(['JWT_SECRET_FILE', 'DATABASE_URL_FILE', 'S3_ACCESS_KEY_ID_FILE', 'S3_SECRET_ACCESS_KEY_FILE', 'QUEUE_PASSWORD_FILE', 'RESEND_API_KEY_FILE', 'AUTH_MAIL_ENCRYPTION_KEYS_FILE'], '')}
        env.update(APP_ENV='test',QUEUE_BACKEND='database',WORKER_REQUIRE_SANDBOX='false',WORKER_REQUIRE_LIMITS='false',AUTH_MAIL_BACKEND='disabled',AUTH_MAIL_SEND_ENABLED='false',AUTH_REQUIRE_VERIFIED_EMAIL='false',MEDIA_BACKEND='s3',S3_ENDPOINT=endpoint,S3_PUBLIC_ENDPOINT=endpoint,
            S3_BUCKET='nextphase-smoke',S3_ACCESS_KEY_ID=access,S3_SECRET_ACCESS_KEY=secret,
            SIGNED_DOWNLOAD_SECONDS='5',NEXTPHASE_SMOKE_S3_CHECKS='1',
            DIRECT_UPLOADS_ENABLED='true',SIGNED_UPLOAD_SECONDS='5',NEXTPHASE_SMOKE_DIRECT='1',
            JWT_SECRET=secrets.token_urlsafe(48))
        # The parent initializes only this disposable local bucket.
        os.environ.update(env)
        sys.path.insert(0,str(ROOT/'apps/api'))
        from app.object_store import client
        ready = False
        last_error = 'not attempted'
        for _ in range(100):
            try:
                client().create_bucket(Bucket='nextphase-smoke')
                client().put_object(Bucket='nextphase-smoke',Key='readiness',Body=b'ready')
                client().delete_object(Bucket='nextphase-smoke',Key='readiness')
                ready=True;break
            except Exception as error:
                last_error = safe_error(error)
                state = run('inspect','--format','{{.State.Running}}',name,
                            capture_output=True,text=True,timeout=10).stdout.strip()
                if state != 'true':
                    break
                time.sleep(.2)
        if not ready:
            raise RuntimeError(f'Local S3 readiness failed ({last_error}); inspect retained server.log')
        subprocess.run([sys.executable,str(ROOT/'scripts/smoke_e2e.py'),
            '--output-dir',str(directory/'workflow')],cwd=ROOT,env=env,check=True,timeout=300)
        print('Local S3 workflow evidence:',directory/'workflow')
    finally:
        result = subprocess.run(docker+['logs',name],env=docker_env,capture_output=True,text=True,timeout=10)
        log = sanitized_log(result.stdout+result.stderr, access, secret)
        (directory/'server.log').write_text(log)
        if sys.exc_info()[0] is not None:
            print('Local S3 diagnostic log (last 35 lines):', file=sys.stderr)
            print('\n'.join(log.splitlines()[-35:]), file=sys.stderr)
        subprocess.run(docker+['rm','-fv',name],env=docker_env,stdout=subprocess.DEVNULL,timeout=15)
        config.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
