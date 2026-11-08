"""Real API + separate sender restart proof, with local-only provider simulation."""
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from cryptography.fernet import Fernet
import httpx

ROOT=Path(__file__).resolve().parents[1]


def main():
    evidence=ROOT/'.data'/('email-delivery-smoke-'+uuid.uuid4().hex);evidence.mkdir(parents=True)
    protected=[]
    with tempfile.TemporaryDirectory(prefix='nextphase-email-proof-') as temporary:
        private=Path(temporary)/'sink';email=uuid.uuid4().hex+'@example.com'
        password=secrets.token_urlsafe(24);new_password=secrets.token_urlsafe(24)
        env=os.environ.copy()
        env.update(APP_ENV='test',PYTHONPATH=str(ROOT/'apps/api'),DATABASE_URL='sqlite:///'+temporary+'/db.sqlite3',
            STORAGE_DIR=temporary+'/media',JWT_SECRET=secrets.token_urlsafe(48),MEDIA_BACKEND='local',DIRECT_UPLOADS_ENABLED='false',
            AUTH_MAIL_BACKEND='resend',AUTH_MAIL_SEND_ENABLED='true',AUTH_MAIL_DIR=temporary+'/mail',
            AUTH_MAIL_FROM='noreply@auth.example.com',RESEND_API_KEY='re_'+secrets.token_urlsafe(24),
            AUTH_MAIL_ENCRYPTION_KEYS=Fernet.generate_key().decode(),AUTH_MAIL_RECIPIENTS=email,
            AUTH_MAIL_DAILY_LIMIT='5',AUTH_MAIL_MONTHLY_LIMIT='20',AUTH_REQUIRE_VERIFIED_EMAIL='true',
            NEXTPHASE_MAIL_FIXTURE='local-only',NEXTPHASE_MAIL_FIXTURE_DIR=str(private),
            AUTH_LOGIN_ACCOUNT_LIMIT='10',AUTH_LOGIN_IP_LIMIT='50',AUTH_REGISTER_IP_LIMIT='10',AUTH_PASSWORD_LIMIT='5')
        protected.extend([email,password,new_password,env['RESEND_API_KEY'],env['AUTH_MAIL_ENCRYPTION_KEYS'],env['JWT_SECRET']])
        subprocess.run([sys.executable,'-m','app.migrate'],cwd=ROOT,env=env,check=True,timeout=30)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        api=None;sender=None
        def stop(child):
            if child and child.poll() is None:
                child.terminate()
                try:child.wait(timeout=10)
                except subprocess.TimeoutExpired:child.kill();child.wait()
        def run_code(code):
            return subprocess.check_output([sys.executable,'-c',code],env=env,cwd=ROOT,text=True,timeout=30)
        with (evidence/'api.log').open('w') as api_log,(evidence/'sender.log').open('w') as sender_log,\
                httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=30) as client:
            def start_api():
                child=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port),'--no-proxy-headers'],
                    cwd=ROOT,env=env,stdout=api_log,stderr=subprocess.STDOUT)
                for _ in range(100):
                    try:
                        if client.get('/ready').status_code==200:return child
                    except httpx.HTTPError:pass
                    if child.poll() is not None:raise RuntimeError('Disposable email API failed')
                    time.sleep(.1)
                stop(child);raise RuntimeError('Disposable email API readiness timeout')
            def start_sender(once=False):
                return subprocess.Popen([sys.executable,str(ROOT/'scripts/mail_fixture_worker.py')]+(['--once'] if once else []),
                    cwd=ROOT,env=env,stdout=sender_log,stderr=subprocess.STDOUT)
            def wait_accepted(count):
                deadline=time.monotonic()+20
                while time.monotonic()<deadline:
                    state=json.loads(run_code('from app.mail_worker import report; import json; print(json.dumps(report()))'))
                    if state['states'].get('accepted',0)>=count:return
                    if sender.poll() is not None:raise RuntimeError('Local fixture sender stopped unexpectedly')
                    time.sleep(.1)
                raise RuntimeError('Local fixture delivery timeout')
            def code_for(subject):
                messages=[json.loads(path.read_text()) for path in private.glob('*.json')]
                selected=[message for message in messages if message['subject']==subject]
                assert len(selected)==1
                code=re.search(r'\n([A-Za-z0-9_-]{43})\n',selected[0]['text']).group(1)
                protected.append(code);return code
            try:
                api=start_api()
                first=client.post('/api/v1/auth/register',json={'email':email,'password':password});assert first.status_code==201
                pair=first.json();protected.extend([pair['access_token'],pair['refresh_token']]);owner={'Authorization':'Bearer '+pair['access_token']}
                other_email=uuid.uuid4().hex+'@example.com';protected.append(other_email)
                other=client.post('/api/v1/auth/register',json={'email':other_email,'password':password}).json()
                protected.extend([other['access_token'],other['refresh_token']])
                assert client.get('/api/v1/auth/recovery-capabilities').json()=={'delivery':'email','verification_enforced':True}
                upload={'file_name':'fixture.mp4','total_bytes':10,'title':'Mail proof','style':'vlog','desired_seconds':15,
                    'rights_confirmed':True,'consent_version':'upload-rights-v1'}
                headers={**owner,'Idempotency-Key':uuid.uuid4().hex}
                assert client.post('/api/v1/upload-sessions',headers=headers,json=upload).status_code==403
                assert client.post('/api/v1/auth/email-verification/request',headers=owner).status_code==202
                # Restart API before any sender exists: delivery intent must survive.
                stop(api);api=start_api()
                sender=start_sender(True);assert sender.wait(timeout=20)==99
                # All fixture writers stopped before simulating an expired sender lease.
                stop(api)
                run_code("from app.db import SessionLocal,engine; from app.models import MailOutbox,MailBudget,utcnow; from sqlalchemy import update; from datetime import timedelta;\nwith SessionLocal.begin() as db:\n db.execute(update(MailOutbox).where(MailOutbox.state=='sending').values(lease_until=utcnow()-timedelta(seconds=1)))\n db.execute(update(MailBudget).values(next_send_at=utcnow()-timedelta(seconds=1)))\nengine.dispose()")
                api=start_api();sender=start_sender();wait_accepted(1)
                verification=code_for('Confirm your NextPhase Shorts email')
                assert client.post('/api/v1/auth/email-verification/confirm',json={'code':verification}).status_code==204
                assert client.get('/api/v1/me',headers=owner).json()['email_verification_method']=='resend'
                admitted=client.post('/api/v1/upload-sessions',headers=headers,json=upload);assert admitted.status_code==201
                assert client.post('/api/v1/upload-sessions/'+admitted.json()['id']+'/abort',headers=owner).status_code==200
                assert client.post('/api/v1/auth/password-reset/request',json={'email':email}).status_code==202
                wait_accepted(2);reset=code_for('Reset your NextPhase Shorts password')
                assert client.post('/api/v1/auth/password-reset/confirm',json={'code':reset,'new_password':new_password}).status_code==204
                assert client.get('/api/v1/me',headers=owner).status_code==401
                assert client.post('/api/v1/auth/refresh',json={'refresh_token':pair['refresh_token'],'rotation_key':str(uuid.uuid4())}).status_code==401
                assert client.get('/api/v1/me',headers={'Authorization':'Bearer '+other['access_token']}).status_code==200
                assert client.post('/api/v1/auth/password-reset/confirm',json={'code':reset,'new_password':new_password}).status_code==400
                assert client.post('/api/v1/auth/login',json={'email':email,'password':new_password}).status_code==200
                remaining=json.loads(run_code("from app.db import SessionLocal; from app.models import MailOutbox; from sqlalchemy import select,func; import json;\nwith SessionLocal() as db: print(json.dumps({'payloads':db.scalar(select(func.count()).select_from(MailOutbox).where(MailOutbox.payload.is_not(None)))}))"))
                assert remaining['payloads']==0
                report={'transport':'local MockTransport only; Resend not contacted','api_restarted':True,
                    'sender_crashed_after_simulated_acceptance':True,'durable_same_body_idempotency':'passed',
                    'verified_upload_gate':'passed','reset_and_refresh_revocation':'passed','other_owner_preserved':True,
                    'accepted_ciphertext_removed':True,'lease':'advanced only with disposable writers stopped'}
            finally:stop(sender);stop(api)
        logs=(evidence/'api.log').read_text()+(evidence/'sender.log').read_text()
        assert all(value not in logs for value in protected)
    assert not Path(temporary).exists();report['private_fixture_cleanup']='passed'
    (evidence/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Email delivery:',json.dumps(report));print('Email evidence:',evidence)


if __name__=='__main__':main()
