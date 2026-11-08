"""Disposable Valkey AOF restart plus real HTTP/Arq rendering; no paid services."""
import asyncio
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
IMAGE='valkey/valkey:8.1-alpine@sha256:2602ace2be6569bc2bbb06f873776516ab9089821525be34f4305c67eb9db02a'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--s3',action='store_true');args=parser.parse_args()
    name='nextphase-queue-smoke-'+uuid.uuid4().hex[:12]
    evidence=ROOT/'.data'/name;evidence.mkdir(parents=True,mode=0o700)
    password=secrets.token_urlsafe(48);configuration=evidence/'valkey.conf'
    configuration.write_text('bind 0.0.0.0\nprotected-mode yes\nrequirepass '+password+
        '\ndir /data\nappendonly yes\nappendfsync always\nmaxmemory 64mb\nmaxmemory-policy noeviction\nsave ""\n')
    configuration.chmod(0o600)
    docker_env={**os.environ, **dict.fromkeys(['JWT_SECRET_FILE', 'DATABASE_URL_FILE', 'S3_ACCESS_KEY_ID_FILE', 'S3_SECRET_ACCESS_KEY_FILE', 'QUEUE_PASSWORD_FILE', 'RESEND_API_KEY_FILE', 'AUTH_MAIL_ENCRYPTION_KEYS_FILE'], '')}
    for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):docker_env.pop(key,None)
    docker=['docker','--context','default'] if os.name=='nt' else ['docker','--host=unix:///var/run/docker.sock']
    def run(*args,**kwargs):return subprocess.run(docker+list(args),env=docker_env,check=True,timeout=60,**kwargs)
    try:
        run('create','--name',name,'-p','127.0.0.1::6379',IMAGE,'valkey-server','/data/valkey.conf',stdout=subprocess.DEVNULL)
        run('cp',str(configuration),name+':/data/valkey.conf',stdout=subprocess.DEVNULL)
        run('start',name,stdout=subprocess.DEVNULL)
        port=run('port',name,'6379/tcp',capture_output=True,text=True).stdout.strip().rsplit(':',1)[1]
        env={**os.environ, **dict.fromkeys(['JWT_SECRET_FILE', 'DATABASE_URL_FILE', 'S3_ACCESS_KEY_ID_FILE', 'S3_SECRET_ACCESS_KEY_FILE', 'QUEUE_PASSWORD_FILE', 'RESEND_API_KEY_FILE', 'AUTH_MAIL_ENCRYPTION_KEYS_FILE'], '')};env.update(APP_ENV='test',QUEUE_BACKEND='valkey',QUEUE_HOST='127.0.0.1',QUEUE_PORT=port,
            QUEUE_PASSWORD=password,QUEUE_TLS='false',WORKER_REQUIRE_SANDBOX='false',WORKER_REQUIRE_LIMITS='false',
            AUTH_MAIL_BACKEND='disabled',AUTH_MAIL_SEND_ENABLED='false',AUTH_REQUIRE_VERIFIED_EMAIL='false',
            JWT_SECRET=secrets.token_urlsafe(48),NEXTPHASE_SMOKE_BROKER='1')
        os.environ.update(env);sys.path.insert(0,str(ROOT/'apps/api'))
        from app.broker import connect,loads
        async def ready():
            for _ in range(50):
                try:return await connect()
                except Exception:await asyncio.sleep(.1)
            raise RuntimeError('Local durable queue failed readiness; inspect sanitized server.log')
        generation=str(uuid.uuid4());job_id='np:restart:'+generation
        async def before():
            redis=await ready()
            try:
                await redis.enqueue_job('render_next',generation,_job_id=job_id,_queue_name='np:restart')
                payload=await redis.get('arq:job:'+job_id);assert loads(payload)['a']==[generation]
                return hashlib.sha256(payload).hexdigest()
            finally:await redis.aclose()
        digest=asyncio.run(before())
        run('kill','--signal','KILL',name,stdout=subprocess.DEVNULL);run('start',name,stdout=subprocess.DEVNULL)
        # Docker can assign a different ephemeral host port when restarting.
        port=run('port',name,'6379/tcp',capture_output=True,text=True).stdout.strip().rsplit(':',1)[1]
        env['QUEUE_PORT']=port;os.environ['QUEUE_PORT']=port
        from app.config import get_settings
        get_settings.cache_clear()
        async def after():
            redis=await ready()
            try:
                payload=await redis.get('arq:job:'+job_id)
                assert hashlib.sha256(payload).hexdigest()==digest
                assert await redis.zscore('np:restart',job_id) is not None
                await redis.delete('arq:job:'+job_id);await redis.zrem('np:restart',job_id)
            finally:await redis.aclose()
        asyncio.run(after())
        report={'queue':'Valkey + Arq, strict JSON only','aof_hard_restart':'exact accepted message retained',
            'appendfsync':'always','eviction':'disabled','credentials_logged':False,
            'resource_scope':'standalone development workflow; strict host containment acceptance separate'}
        (evidence/'broker-report.json').write_text(json.dumps(report,indent=2)+'\n')
        print('Durable broker:',json.dumps(report),flush=True)
        command=[sys.executable,str(ROOT/'scripts/smoke_object_store.py')] if args.s3 else [sys.executable,str(ROOT/'scripts/smoke_e2e.py'),'--output-dir',str(evidence/'workflow')]
        subprocess.run(command,
            cwd=ROOT,env=env,check=True,timeout=360)
        print('Broker evidence:',evidence)
    finally:
        log=subprocess.run(docker+['logs',name],env=docker_env,capture_output=True,text=True,timeout=15)
        safe=(log.stdout+log.stderr).replace(password,'[REDACTED]')
        (evidence/'server.log').write_text(safe)
        subprocess.run(docker+['rm','-fv',name],env=docker_env,stdout=subprocess.DEVNULL,timeout=15)
        configuration.unlink(missing_ok=True)


if __name__=='__main__':main()
