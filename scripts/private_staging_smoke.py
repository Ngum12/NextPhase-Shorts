"""Isolated real Caddy HTTPS + API/render + private OTLP/alert + budget acceptance.

No existing target, public listener, provider call or phone trust-store changes.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import time
import uuid
import httpx
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--caddy',required=True);args=parser.parse_args()
    evidence=ROOT/'.data'/('private-staging-'+uuid.uuid4().hex);evidence.mkdir(mode=0o700,parents=True)
    with tempfile.TemporaryDirectory(prefix='nextphase-private-staging-') as temporary,ExitStack() as cleanup:
        directory=Path(temporary);roots={role:directory/role for role in ('edge','agent','receiver','offline')}
        for root in roots.values():root.mkdir(mode=0o700)
        sys.path.insert(0,str(ROOT/'apps/api'))
        from app.staging_setup import provision
        from app.budget_control import reconcile,write_state,COMPONENTS
        provision(roots)
        ports=[]
        for _ in range(4):
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));ports.append(sock.getsockname()[1])
        api_port,receiver_port,edge_port,ops_port=ports
        env={**os.environ,**dict.fromkeys(['JWT_SECRET_FILE','DATABASE_URL_FILE','S3_ACCESS_KEY_ID_FILE','S3_SECRET_ACCESS_KEY_FILE','QUEUE_PASSWORD_FILE','RESEND_API_KEY_FILE','AUTH_MAIL_ENCRYPTION_KEYS_FILE','RESTORE_JOURNAL_KEY_FILE'],'')}
        env.update(APP_ENV='test',PYTHONPATH=str(ROOT/'apps/api'),JWT_SECRET=secrets.token_urlsafe(48),DATABASE_URL='sqlite:///'+temporary+'/app.db',STORAGE_DIR=temporary+'/media',
            RESTORE_JOURNAL_DIR=temporary+'/journal',RESTORE_JOURNAL_KEY=secrets.token_urlsafe(32),QUEUE_BACKEND='database',MEDIA_BACKEND='local',DIRECT_UPLOADS_ENABLED='false',
            AUTH_MAIL_BACKEND='disabled',AUTH_MAIL_SEND_ENABLED='false',AUTH_REQUIRE_VERIFIED_EMAIL='false',WORKER_REQUIRE_SANDBOX='false',WORKER_REQUIRE_LIMITS='false',
            WORKER_POLL_SECONDS='.1',WORKER_HEARTBEAT_SECONDS='1',MIN_FREE_DISK_BYTES='0',AUTH_LOGIN_IP_LIMIT='2',
            OPERATOR_RECEIVER_TOKEN='',OPERATOR_RECEIVER_TOKEN_FILE=str(roots['agent']/'receiver.token'),OPERATOR_SINK_DIR=temporary+'/sink',BUDGET_STATE_FILE=temporary+'/budget.json')
        # A fresh Fernet key includes required URL-safe base64 padding.
        from cryptography.fernet import Fernet
        env['RESTORE_JOURNAL_KEY']=Fernet.generate_key().decode()
        now=datetime.now(timezone.utc)
        policy={'version':1,'currency':'USD','budget_usd':'10','approved':True,'mode':'local_fixture'}
        usage={'version':1,'currency':'USD','mode':'local_fixture','window_start':(now-timedelta(days=1)).isoformat(),'window_end':(now+timedelta(days=1)).isoformat(),
            'updated_at':now.isoformat(),'components':{name:'0' for name in COMPONENTS}}
        write_state(directory/'budget.json',reconcile(policy,usage))
        def run(*command,**kwargs):return subprocess.run(command,cwd=ROOT,env=env,check=True,timeout=90,**kwargs)
        log=cleanup.enter_context((evidence/'services.log').open('w'))
        for module,options in [('app.migrate',[]),('app.restore_replay',['--init']),('app.restore_replay',['--bind','--offline'])]:run(sys.executable,'-m',module,*options,stdout=log,stderr=subprocess.STDOUT)
        config=(ROOT/'deploy/private-staging/Caddyfile').read_text().replace(':8443',':'+str(edge_port)).replace(':9443',':'+str(ops_port))
        config=config.replace('/var/nextphase/staging-edge',str(roots['edge'])).replace('api:8000','127.0.0.1:'+str(api_port)).replace('operator-receiver:9090','127.0.0.1:'+str(receiver_port))
        config=config.replace('    tls ','    bind 127.0.0.1\n    tls ').replace('max_size 315MB','max_size 128KiB')
        config_path=directory/'Caddyfile';config_path.write_text(config)
        run(args.caddy,'validate','--config',str(config_path),'--adapter','caddyfile',stdout=log,stderr=subprocess.STDOUT)
        children=[]
        def start(*command):
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT);children.append(process);return process
        def stop(process):
            if process.poll() is not None:return
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        cleanup.callback(lambda:[stop(process) for process in reversed(children)])
        start(sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(api_port),'--no-proxy-headers','--no-access-log')
        start(sys.executable,'-m','uvicorn','app.operator_receiver:app','--host','127.0.0.1','--port',str(receiver_port),'--no-proxy-headers','--no-access-log')
        worker=start(sys.executable,'-m','app.worker')
        start(args.caddy,'run','--config',str(config_path),'--adapter','caddyfile')
        context=ssl.create_default_context(cafile=str(roots['agent']/'root.crt'))
        base=f'https://127.0.0.1:{edge_port}';ops=f'https://localhost:{ops_port}'
        with httpx.Client(base_url=base,verify=context,trust_env=False,timeout=30) as client:
            for _ in range(100):
                try:
                    if client.get('/ready').status_code==200:break
                except httpx.HTTPError:pass
                if any(process.poll() is not None for process in children):raise RuntimeError('Private rehearsal child exited; inspect private log')
                time.sleep(.1)
            else:raise RuntimeError('Private HTTPS readiness failed')
            run(sys.executable,'-m','app.staging_check','--url',base,'--ca-file',str(roots['agent']/'root.crt'),stdout=log,stderr=subprocess.STDOUT)
            with UntrustedCertificateRejected():
                with httpx.Client(trust_env=False) as untrusted:untrusted.get(base+'/health')
            assert client.get('/docs').status_code==404 and client.get('/v1/traces').status_code==404
            assert client.post('/api/v1/auth/login',content=b'x'*(129*1024)).status_code==413
            response=client.post('/api/v1/auth/register',json={'email':uuid.uuid4().hex+'@example.com','password':secrets.token_urlsafe(20)});assert response.status_code==201
            headers={'Authorization':'Bearer '+response.json()['access_token']}
            source=directory/'source.mp4';run('ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=30','-t','2','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(source))
            invalid=client.post('/api/v1/upload-sessions',headers={**headers,'Idempotency-Key':str(uuid.uuid4())},json={'file_name':'source.mp4','total_bytes':20,'title':'invalid','style':'vlog','desired_seconds':61,'rights_confirmed':True,'consent_version':'upload-rights-v1'})
            assert invalid.status_code==422
            response=client.post('/api/v1/jobs',headers=headers,files={'file':('source.mp4',source.read_bytes(),'video/mp4')},data={'title':'TLS fixture','style':'vlog','desired_seconds':'5','rights_confirmed':'true','consent_version':'upload-rights-v1'})
            assert response.status_code==201,response.text
            jid=response.json()['id']
            for _ in range(300):
                job=client.get('/api/v1/jobs/'+jid,headers=headers).json()
                if job['status']=='succeeded':break
                if job['status'] in ('failed','cancelled'):raise RuntimeError('Fixture render failed')
                time.sleep(.1)
            else:raise RuntimeError('Fixture render timeout')
            result=client.get('/api/v1/jobs/'+jid+'/download',headers=headers);assert result.status_code==200
            output=directory/'output.mp4';output.write_bytes(result.content)
            probe=json.loads(run('ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output),capture_output=True,text=True).stdout)
            video=next(stream for stream in probe['streams'] if stream['codec_type']=='video')
            assert (video['width'],video['height'])==(1080,1920) and 0<float(probe['format']['duration'])<=5
            run('ffmpeg','-nostdin','-v','error','-i',str(output),'-f','null','-',stdout=log,stderr=subprocess.STDOUT)
            run(sys.executable,'-m','app.operator_agent','--url',ops,'--ca-file',str(roots['agent']/'root.crt'),'--once',stdout=log,stderr=subprocess.STDOUT)
            stop(worker)
            # Only a stopped fixture pulse ages; no live lease/production clock changes.
            with sqlite3.connect(directory/'app.db') as db:db.execute('UPDATE worker_pulses SET heartbeat_at=?,stopped_at=NULL',((now-timedelta(seconds=200)).isoformat(),))
            run(sys.executable,'-m','app.operator_agent','--url',ops,'--ca-file',str(roots['agent']/'root.crt'),'--once',stdout=log,stderr=subprocess.STDOUT)
            with sqlite3.connect(directory/'sink/received.sqlite3') as db:
                assert db.execute("SELECT sum(count) FROM events WHERE kind='traces'").fetchone()[0]>0
                alerts=[json.loads(row[0]) for row in db.execute("SELECT body FROM events WHERE kind='alerts'")]
                assert any('no_fresh_workers' in item['issues'] for item in alerts)
            usage['components']['worker']='10';write_state(directory/'budget.json',reconcile(policy,usage))
            paused=client.post('/api/v1/upload-sessions',headers={**headers,'Idempotency-Key':str(uuid.uuid4())},json={'file_name':'source.mp4','total_bytes':20,'title':'paused','style':'vlog','desired_seconds':5,'rights_confirmed':True,'consent_version':'upload-rights-v1'})
            assert paused.status_code==503 and client.get('/api/v1/me',headers=headers).status_code==200
            run(sys.executable,'-m','app.operator_agent','--url',ops,'--ca-file',str(roots['agent']/'root.crt'),'--once',stdout=log,stderr=subprocess.STDOUT)
            with sqlite3.connect(directory/'sink/received.sqlite3') as db:
                assert any('budget_admission_paused' in json.loads(row[0])['issues'] for row in db.execute("SELECT body FROM events WHERE kind='alerts'"))
            for index in range(3):
                failed=client.post('/api/v1/auth/login',headers={'X-Forwarded-For':f'198.51.100.{index+1}'},json={'email':'missing@example.com','password':'synthetic-wrong'})
            assert failed.status_code==429
            # Force a proxy failure with private-looking query/header sentinels.
            stop(children[0])
            client.get('/health?private-sentinel-do-not-log=1',headers={'Authorization':'Bearer private-header-do-not-log'})
            log.flush()
            text=(evidence/'services.log').read_text()
            assert 'private-sentinel-do-not-log' not in text and 'private-header-do-not-log' not in text
            report={'https_certificate_verification':'passed; untrusted root rejected','edge_body_and_private_routes':'passed','forged_forwarded_ip_rate_limit':'passed',
                'upload_render_download':'1080x1920; <=5 seconds; decoded','private_otlp_delivery':'acknowledged','worker_failure_alert_delivery':'acknowledged',
                'budget_stop':'new admissions refused; existing reads allowed','cost_scope':'synthetic local fixture; not real provider spending',
                'production_ready':False,'pending':['approved hosting and public certificate','private cloud storage/IAM acceptance','provider bill evidence and quotas','offsite key/journal/backup custody','privacy/license/provider signoff']}
            (evidence/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));print('Evidence:',evidence)


class UntrustedCertificateRejected:
    def __enter__(self):return self
    def __exit__(self,kind,value,traceback):
        if kind is not None and issubclass(kind,httpx.ConnectError) and 'CERTIFICATE_VERIFY_FAILED' in str(value):return True
        if kind is None:raise AssertionError('Untrusted certificate was accepted')
        return False

if __name__=='__main__':main()
