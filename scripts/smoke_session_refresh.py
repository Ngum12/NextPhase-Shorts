"""Real HTTP refresh/restart proof with a disposable DB; prints no credentials."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import uuid
import httpx
import jwt

ROOT=Path(__file__).resolve().parents[1]


def main():
    evidence=ROOT/'.data'/('session-refresh-smoke-'+uuid.uuid4().hex)
    evidence.mkdir(parents=True)
    secret_values=[]
    with tempfile.TemporaryDirectory(prefix='nextphase-refresh-') as temporary:
        env={**os.environ, **dict.fromkeys(['JWT_SECRET_FILE', 'DATABASE_URL_FILE', 'S3_ACCESS_KEY_ID_FILE', 'S3_SECRET_ACCESS_KEY_FILE', 'QUEUE_PASSWORD_FILE', 'RESEND_API_KEY_FILE', 'AUTH_MAIL_ENCRYPTION_KEYS_FILE', 'RESTORE_JOURNAL_KEY_FILE', 'RESTORE_JOURNAL_KEY', 'RESTORE_JOURNAL_DIR'], '')}
        env.update(APP_ENV='test',QUEUE_BACKEND='database',WORKER_REQUIRE_SANDBOX='false',WORKER_REQUIRE_LIMITS='false',PYTHONPATH=str(ROOT/'apps/api'),DATABASE_URL='sqlite:///'+temporary+'/db.sqlite3',
            STORAGE_DIR=temporary+'/media',JWT_SECRET=secrets.token_urlsafe(48),AUTH_MAIL_BACKEND='disabled',AUTH_MAIL_SEND_ENABLED='false',AUTH_REQUIRE_VERIFIED_EMAIL='false',
            AUTH_MAIL_DIR=temporary+'/mail',MEDIA_BACKEND='local',DIRECT_UPLOADS_ENABLED='false',AUTH_ACCESS_MINUTES='1',
            AUTH_REFRESH_IP_LIMIT='120',AUTH_REGISTER_IP_LIMIT='10',AUTH_LOGIN_ACCOUNT_LIMIT='10',AUTH_LOGIN_IP_LIMIT='30')
        subprocess.run([sys.executable,'-m','app.migrate'],cwd=ROOT,env=env,check=True,timeout=30)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        process=None
        def stop():
            if process:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        with (evidence/'api.log').open('w') as log,httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=30) as client:
            def start():
                child=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port),'--no-proxy-headers'],
                    cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                for _ in range(100):
                    try:
                        if client.get('/ready').status_code==200:return child
                    except httpx.HTTPError:pass
                    if child.poll() is not None:raise RuntimeError('Disposable refresh API startup failed')
                    time.sleep(.1)
                child.terminate();child.wait(timeout=10)
                raise RuntimeError('Disposable refresh API readiness timeout')
            def rotate(pair,key):
                return client.post('/api/v1/auth/refresh',json={'refresh_token':pair['refresh_token'],'rotation_key':key})
            def remember(pair):
                secret_values.extend([pair['access_token'],pair['refresh_token']]);return pair
            def headers(pair):return {'Authorization':'Bearer '+pair['access_token']}
            try:
                process=start();password=secrets.token_urlsafe(24);email=uuid.uuid4().hex+'@example.com'
                secret_values.extend([password,email])
                response=client.post('/api/v1/auth/register',json={'email':email,'password':password})
                assert response.status_code==201;first=remember(response.json())
                uid=client.get('/api/v1/me',headers=headers(first)).json()['id']
                response=client.post('/api/v1/auth/login',json={'email':email,'password':password})
                assert response.status_code==200;other=remember(response.json())
                # Expire only a signed disposable fixture JWT; no application clock
                # or production row is changed and no debug/test endpoint exists.
                claims=jwt.decode(first['access_token'],env['JWT_SECRET'],algorithms=['HS256'],audience='nextphase-shorts-mobile')
                claims['iat']=int(time.time())-120;claims['exp']=int(time.time())-60
                expired=jwt.encode(claims,env['JWT_SECRET'],algorithm='HS256');secret_values.append(expired)
                assert client.get('/api/v1/me',headers={'Authorization':'Bearer '+expired}).status_code==401
                key=str(uuid.uuid4());secret_values.append(key)
                response=rotate(first,key);assert response.status_code==200
                second=remember(response.json())
                stop();process=start()
                # Simulate a committed refresh whose response was lost, then retry
                # the durable old token/key after API and client restart.
                retry=rotate(first,key);assert retry.status_code==200
                assert retry.json()['access_token']==second['access_token']
                assert retry.json()['refresh_token']==second['refresh_token']
                assert client.get('/api/v1/me',headers=headers(second)).json()['id']==uid
                assert rotate(first,str(uuid.uuid4())).status_code==401
                assert client.get('/api/v1/me',headers=headers(second)).status_code==401
                assert rotate(second,str(uuid.uuid4())).status_code==401
                assert client.get('/api/v1/me',headers=headers(other)).status_code==200
                third=remember(rotate(other,str(uuid.uuid4())).json())
                assert client.post('/api/v1/auth/refresh/logout',json={'refresh_token':other['refresh_token']}).status_code==204
                assert client.get('/api/v1/me',headers=headers(third)).status_code==401
                assert rotate(third,str(uuid.uuid4())).status_code==401
                report={'api_restarted':True,'lost_response_recovered':'same pair','reused_token':'family revoked',
                    'other_login_preserved':True,'refresh_logout':'revoked all family access',
                    'expired_access':'signed past-expiry fixture rejected; refresh accepted',
                    'credentials_in_logs':False}
            finally:stop()
        contents=(evidence/'api.log').read_text()
        assert all(value not in contents for value in secret_values)
    assert not Path(temporary).exists();report['temporary_cleanup']='passed'
    (evidence/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Session refresh:',json.dumps(report));print('Refresh evidence:',evidence)


if __name__=='__main__':main()
