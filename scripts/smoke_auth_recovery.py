"""Disposable local inbox/API proof. No real email, provider or existing DB is used."""
import json,os,secrets,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]


def main():
    evidence=ROOT/'.data'/('auth-recovery-smoke-'+uuid.uuid4().hex);evidence.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='nextphase-auth-smoke-') as temporary:
        inbox=Path(temporary)/'private-mail';env=os.environ.copy()
        env.update(APP_ENV='test',QUEUE_BACKEND='database',WORKER_REQUIRE_SANDBOX='false',WORKER_REQUIRE_LIMITS='false',PYTHONPATH=str(ROOT/'apps/api'),DATABASE_URL='sqlite:///'+temporary+'/db.sqlite3',
            STORAGE_DIR=temporary+'/media',JWT_SECRET=secrets.token_urlsafe(48),MEDIA_BACKEND='local',DIRECT_UPLOADS_ENABLED='false',
            AUTH_MAIL_BACKEND='file',AUTH_MAIL_SEND_ENABLED='false',AUTH_REQUIRE_VERIFIED_EMAIL='false',AUTH_MAIL_DIR=str(inbox),AUTH_ACTION_EMAIL_LIMIT='3',AUTH_ACTION_MINUTES='15',
            AUTH_LOGIN_ACCOUNT_LIMIT='5',AUTH_LOGIN_IP_LIMIT='30',AUTH_REGISTER_IP_LIMIT='10',AUTH_PASSWORD_LIMIT='5',AUTH_WINDOW_SECONDS='900')
        subprocess.run([sys.executable,'-m','app.migrate'],cwd=ROOT,env=env,check=True,timeout=30)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        base=f'http://127.0.0.1:{port}';process=None;proofs=[]
        def stop():
            if process:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        with (evidence/'api.log').open('w') as log,httpx.Client(base_url=base,trust_env=False,timeout=30) as client:
            def start():
                child=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port),'--no-proxy-headers'],
                    cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                for _ in range(100):
                    try:
                        if client.get('/ready').status_code==200:return child
                    except httpx.HTTPError:pass
                    if child.poll() is not None:raise RuntimeError('Disposable recovery API startup failed')
                    time.sleep(.1)
                child.terminate();child.wait(timeout=10);raise RuntimeError('Disposable recovery API readiness timeout')
            def private_code(purpose,recipient,previous=None):
                deadline=time.monotonic()+10
                while True:
                    rows=[json.loads(path.read_text()) for path in inbox.glob('*.json')]
                    rows=[row for row in rows if row['purpose']==purpose and row['recipient']==recipient and row['code']!=previous]
                    if rows:
                        code=max(rows,key=lambda row:row['expires_at'])['code'];proofs.append(code);return code
                    if time.monotonic()>deadline:raise RuntimeError('Private local test message not prepared')
                    time.sleep(.05)
            try:
                process=start();password=secrets.token_urlsafe(24);new_password=secrets.token_urlsafe(24)
                email=uuid.uuid4().hex+'@example.com';other_email=uuid.uuid4().hex+'@example.com'
                def register(address):
                    response=client.post('/api/v1/auth/register',json={'email':address,'password':password});assert response.status_code==201
                    return {'Authorization':'Bearer '+response.json()['access_token']}
                owner,other=register(email),register(other_email)
                uid=client.get('/api/v1/me',headers=owner).json()['id']
                assert client.get('/api/v1/auth/recovery-capabilities').json()['delivery']=='local_file'
                assert client.post('/api/v1/auth/email-verification/request',headers=owner).status_code==202
                verify=private_code('verify',email)
                assert client.post('/api/v1/auth/email-verification/confirm',json={'code':verify}).status_code==204
                assert client.get('/api/v1/me',headers=owner).json()['email_verification_method']=='local_file'
                known=client.post('/api/v1/auth/password-reset/request',json={'email':email})
                absent=client.post('/api/v1/auth/password-reset/request',json={'email':uuid.uuid4().hex+'@example.com'})
                assert known.status_code==absent.status_code==202 and known.json()==absent.json()=={'status':'accepted'}
                code=private_code('reset',email)
                stop();process=start()
                response=client.post('/api/v1/auth/password-reset/confirm',json={'code':code,'new_password':new_password})
                assert response.status_code==204
                assert client.get('/api/v1/me',headers=owner).status_code==401
                assert client.get('/api/v1/me',headers=other).status_code==200
                assert client.post('/api/v1/auth/password-reset/confirm',json={'code':code,'new_password':new_password}).status_code==400
                assert client.post('/api/v1/auth/login',json={'email':email,'password':password}).status_code==401
                login=client.post('/api/v1/auth/login',json={'email':email,'password':new_password});assert login.status_code==200
                fresh={'Authorization':'Bearer '+login.json()['access_token']}
                assert client.get('/api/v1/me',headers=fresh).json()['id']==uid
                assert client.post('/api/v1/auth/password-reset/request',json={'email':email}).status_code==202
                pending=private_code('reset',email,code)
                assert client.post('/api/v1/auth/password',headers=fresh,json={'current_password':new_password,'new_password':password}).status_code==204
                assert client.post('/api/v1/auth/password-reset/confirm',json={'code':pending,'new_password':new_password}).status_code==400
                report={'delivery':'private local files only; no outgoing email','verification':'local test proof',
                    'api_restarted':True,'single_use_reset':'passed','old_sessions_revoked':True,'other_account_preserved':True,
                    'same_account_recovered':True,'password_change_invalidates_codes':True,'generic_requests':True}
            finally:stop()
        contents=(evidence/'api.log').read_text()
        assert all(secret not in contents for secret in [*proofs,password,new_password,email,other_email,owner['Authorization'][7:],other['Authorization'][7:]])
    assert not Path(temporary).exists();report['temporary_cleanup']='passed'
    (evidence/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Local authentication recovery:',json.dumps(report));print('Recovery evidence:',evidence)


if __name__=='__main__':main()
