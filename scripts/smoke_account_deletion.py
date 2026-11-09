"""Disposable HTTP/restart account-deletion proof; never uses an existing database."""
import json,os,secrets,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(prefix='nextphase-account-smoke-') as temporary:
        directory=Path(temporary);env={**os.environ, **dict.fromkeys(['JWT_SECRET_FILE', 'DATABASE_URL_FILE', 'S3_ACCESS_KEY_ID_FILE', 'S3_SECRET_ACCESS_KEY_FILE', 'QUEUE_PASSWORD_FILE', 'RESEND_API_KEY_FILE', 'AUTH_MAIL_ENCRYPTION_KEYS_FILE', 'RESTORE_JOURNAL_KEY_FILE', 'RESTORE_JOURNAL_KEY', 'RESTORE_JOURNAL_DIR', 'BUDGET_STATE_FILE'], '')}
        env.update(APP_ENV='test',QUEUE_BACKEND='database',WORKER_REQUIRE_SANDBOX='false',WORKER_REQUIRE_LIMITS='false',AUTH_MAIL_BACKEND='disabled',AUTH_MAIL_SEND_ENABLED='false',AUTH_REQUIRE_VERIFIED_EMAIL='false',AUTH_MAIL_DIR=temporary+'/auth-mail',PYTHONPATH=str(ROOT/'apps/api'),DATABASE_URL='sqlite:///'+temporary+'/db.sqlite3',
            STORAGE_DIR=temporary+'/media',JWT_SECRET=secrets.token_urlsafe(48))
        subprocess.run([sys.executable,'-m','app.migrate'],cwd=ROOT,env=env,check=True,timeout=30)
        source=directory/'source.mp4'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=blue:s=160x90:r=30','-t','2',
            '-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True,timeout=30)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}';process=None
        def stop():
            if process:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        with (directory/'api.log').open('w') as log,httpx.Client(base_url=base,trust_env=False,timeout=30) as client:
            def start():
                child=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port),'--no-proxy-headers'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                for _ in range(100):
                    try:
                        if client.get('/health').status_code==200:return child
                    except httpx.HTTPError:pass
                    if child.poll() is not None:raise RuntimeError('Disposable API startup failed')
                    time.sleep(.1)
                child.terminate();raise RuntimeError('Disposable API readiness timeout')
            try:
                process=start();password=secrets.token_urlsafe(20)
                def register():
                    response=client.post('/api/v1/auth/register',json={'email':uuid.uuid4().hex+'@example.com','password':password})
                    assert response.status_code==201
                    return {'Authorization':'Bearer '+response.json()['access_token']}
                owner,other=register(),register()
                uid=client.get('/api/v1/me',headers=owner).json()['id']
                # Use the server's versioned uploader acknowledgement, not a guessed version.
                sys.path.insert(0,str(ROOT/'apps/api'))
                from app.consent import RIGHTS_VERSION
                def upload(auth):
                    response=client.post('/api/v1/jobs',headers=auth,files={'file':('source.mp4',source.read_bytes(),'video/mp4')},
                        data={'style':'vlog','desired_seconds':'15','title':'Synthetic account deletion',
                              'rights_confirmed':'true','consent_version':RIGHTS_VERSION})
                    assert response.status_code==201,response.text
                    return response.json()['id']
                jid=upload(owner);keep=upload(other);key=str(uuid.uuid4())
                response=client.post('/api/v1/account/delete',headers=owner,json={'current_password':password,'receipt_key':key})
                assert response.status_code==202 and response.json()['media_cleanup']=='scheduled'
                stop();process=start()
                receipt=client.post('/api/v1/account/deletion-receipt',json={'receipt_key':key})
                assert receipt.status_code==200 and receipt.json()['status']=='account_disabled'
                assert client.get('/api/v1/me',headers=owner).status_code==401
                assert client.get('/api/v1/jobs/'+jid,headers=owner).status_code==401
                assert client.get('/api/v1/jobs/'+keep,headers=other).status_code==200
                stop();process=None
                # Only our stopped disposable writers: advance the synthetic record's
                # deadline, not an operator/production clock or an actual waiting claim.
                proof="""from datetime import timedelta
from app.db import SessionLocal
from app.models import AccountDeletion,RenderJob,utcnow
from app.account_deletion import cleanup_accounts
from app.config import get_settings
from app import object_store as store
import sys
uid,jid,keep=sys.argv[1:]
with SessionLocal.begin() as db:db.get(AccountDeletion,uid).cleanup_after=utcnow()-timedelta(seconds=1)
cleanup_accounts()
with SessionLocal() as db:
 assert db.get(AccountDeletion,uid).media_cleaned_at
 assert db.get(RenderJob,jid).media_deleted_at
 other=db.get(RenderJob,keep)
 if get_settings().media_backend=='s3':
  assert not store.client().list_objects_v2(Bucket=get_settings().s3_bucket,Prefix='media/'+uid+'/').get('Contents')
  assert store.client().list_objects_v2(Bucket=get_settings().s3_bucket,Prefix='media/'+other.user_id+'/').get('Contents')
  store.remove_owner(other.user_id)
 else:
  from pathlib import Path
  assert Path(other.source_path).exists()
 assert not (get_settings().storage_dir/uid).exists()
"""
                subprocess.run([sys.executable,'-c',proof,uid,jid,keep],cwd=ROOT,env=env,check=True,timeout=60)
                print(json.dumps({'account_deletion':'passed','api_restarted':True,'receipt_recovered':True,
                    'other_owner_preserved':True,'media_removed':True,'backend':env.get('MEDIA_BACKEND','local'),
                    'deadline':'advanced only after disposable writers stopped'}))
            finally:stop()
if __name__=='__main__':main()
