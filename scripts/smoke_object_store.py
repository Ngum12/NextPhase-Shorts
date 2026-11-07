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
    docker_env = os.environ.copy()
    for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):
        docker_env.pop(key, None)
    docker = ['docker','--host=unix:///var/run/docker.sock'] if os.name != 'nt' else ['docker','--context','default']
    def run(*args, **kwargs):
        return subprocess.run(docker+list(args),env=docker_env,check=True,**kwargs)
    try:
        run('run','-d','--name',name,'-p','127.0.0.1::8333',
            '--mount',f'type=bind,src={config},dst=/etc/seaweedfs/s3.json,readonly',IMAGE,
            'server','-dir=/data','-ip=127.0.0.1','-master.volumeSizeLimitMB=64',
            '-volume.max=16','-s3','-s3.ip.bind=0.0.0.0',
            '-s3.config=/etc/seaweedfs/s3.json',stdout=subprocess.DEVNULL,timeout=180)
        port = run('port',name,'8333/tcp',capture_output=True,text=True,timeout=10).stdout.strip().rsplit(':',1)[1]
        endpoint = f'http://127.0.0.1:{port}'
        env = os.environ.copy()
        env.update(APP_ENV='test',MEDIA_BACKEND='s3',S3_ENDPOINT=endpoint,S3_PUBLIC_ENDPOINT=endpoint,
            S3_BUCKET='nextphase-smoke',S3_ACCESS_KEY_ID=access,S3_SECRET_ACCESS_KEY=secret,
            SIGNED_DOWNLOAD_SECONDS='5',NEXTPHASE_SMOKE_S3_CHECKS='1',
            JWT_SECRET=secrets.token_urlsafe(48))
        # The parent initializes only this disposable local bucket.
        os.environ.update(env)
        sys.path.insert(0,str(ROOT/'apps/api'))
        from app.object_store import client
        ready = False
        for _ in range(100):
            try:
                client().create_bucket(Bucket='nextphase-smoke')
                client().put_object(Bucket='nextphase-smoke',Key='readiness',Body=b'ready')
                client().delete_object(Bucket='nextphase-smoke',Key='readiness')
                ready=True;break
            except Exception:
                time.sleep(.2)
        if not ready: raise RuntimeError('Local S3 readiness failed; inspect retained server log')
        subprocess.run([sys.executable,str(ROOT/'scripts/smoke_e2e.py'),
            '--output-dir',str(directory/'workflow')],cwd=ROOT,env=env,check=True,timeout=300)
        print('Local S3 workflow evidence:',directory/'workflow')
    finally:
        with (directory/'server.log').open('w') as log:
            subprocess.run(docker+['logs',name],env=docker_env,stdout=log,stderr=subprocess.STDOUT,timeout=10)
        subprocess.run(docker+['rm','-fv',name],env=docker_env,stdout=subprocess.DEVNULL,timeout=15)
        config.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
