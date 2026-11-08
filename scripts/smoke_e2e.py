"""Exercise real HTTP + a separate FFmpeg worker with synthetic media only."""
import argparse
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

ROOT = Path(__file__).resolve().parents[1]
RIGHTS_FORM={'rights_confirmed':'true','consent_version':'upload-rights-v1'}
RIGHTS_JSON={'rights_confirmed':True,'consent_version':'upload-rights-v1'}


def signed_chunk(client, owner, session, offset, chunk):
    import hashlib
    path = '/api/v1/upload-sessions/'+session['id']
    result = client.post(path+'/part-url', headers=owner,
        json={'offset':offset,'sha256':hashlib.sha256(chunk).hexdigest()})
    assert result.status_code == 200, result.text
    grant = result.json()
    if grant['committed']:
        return client.get(path, headers=owner), grant
    with httpx.Client(trust_env=False, timeout=30) as storage:
        uploaded = storage.put(grant['url'], headers=grant['headers'], content=chunk)
        assert uploaded.status_code == 200, uploaded.status_code
    response = client.post(path+'/part-commit/'+grant['grant_id'], headers=owner)
    assert response.status_code == 200, response.text
    return response, grant


def check_api(base_url, output_dir):
    source = output_dir / 'source.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi',
                    '-i', 'testsrc2=size=320x180:rate=30', '-f', 'lavfi',
                    '-i', 'sine=frequency=440:sample_rate=48000', '-t', '5',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)],
                   check=True, timeout=30)
    started = time.monotonic()
    with httpx.Client(base_url=base_url, trust_env=False, timeout=30) as client:
        assert client.get('/health').json()['ok']
        readiness=client.get('/ready')
        assert readiness.status_code==200 and readiness.json()=={'ok':True,'service':'nextphase-shorts'}
        assert client.get('/api/v1/jobs').status_code == 401
        assert all(not style['available'] for style in client.get('/api/v1/styles').json())
        def register():
            response = client.post('/api/v1/auth/register', json={
                'email': f'{uuid.uuid4()}@example.com', 'password': secrets.token_urlsafe(24)})
            assert response.status_code == 201, response.status_code
            return {'Authorization': 'Bearer ' + response.json()['access_token']}
        owner, other = register(), register()
        assert client.get('/api/v1/me/storage',headers=owner).json()['known_reserved_bytes']==0
        denied=client.post('/api/v1/upload-sessions',headers={**owner,'Idempotency-Key':uuid.uuid4().hex},
            json={'file_name':'source.mp4','total_bytes':source.stat().st_size})
        assert denied.status_code==422
        key = uuid.uuid4().hex
        with source.open('rb') as handle:
            response = client.post('/api/v1/jobs', headers={**owner, 'Idempotency-Key': key},
                                   files={'file': ('source.mp4', handle, 'video/mp4')},
                                   data={**RIGHTS_FORM, **({'title': 'Synthetic smoke test', 'style': 'vlog', 'desired_seconds': '15'})})
        assert response.status_code == 201, response.status_code
        job = response.json()
        stored=client.get('/api/v1/me/storage',headers=owner).json()
        assert stored['uninventoried_count']==0 and stored['known_reserved_bytes']>source.stat().st_size
        assert client.get('/api/v1/me/storage',headers=other).json()['known_reserved_bytes']==0
        assert job['status'] == 'queued'
        path = '/api/v1/jobs/' + job['id']
        with source.open('rb') as handle:
            replay = client.post('/api/v1/jobs', headers={**owner, 'Idempotency-Key': key},
                files={'file': ('source.mp4', handle, 'video/mp4')},
                data={**RIGHTS_FORM, **({'title': 'Synthetic smoke test', 'style': 'vlog', 'desired_seconds': '15'})})
        assert replay.status_code == 200 and replay.json()['id'] == job['id']
        assert replay.headers['Idempotency-Replayed'] == 'true'
        assert len(client.get('/api/v1/jobs', headers=owner).json()) == 1
        assert client.get('/api/v1/me/storage',headers=owner).json()['known_reserved_bytes']==stored['known_reserved_bytes']
        assert client.get(path, headers=other).status_code == 404
        assert client.get(path + '/download', headers=other).status_code == 404
        states = ['queued']
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            job = client.get(path, headers=owner).json()
            if job['status'] != states[-1]:
                states.append(job['status'])
            if job['status'] in ('succeeded', 'failed'):
                break
            time.sleep(0.1)
        assert job['status'] == 'succeeded', job.get('error_code', job['status'])
        assert client.get(path + '/download', headers=other).status_code == 404
        assert client.post(path + '/cancel', headers=owner).status_code == 409
        response = client.get(path + '/download', headers=owner)
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('video/mp4')
        assert response.headers['cache-control']=='private, no-store'
        output = output_dir / 'output.mp4'
        output.write_bytes(response.content)
        if os.getenv('NEXTPHASE_SMOKE_S3_CHECKS') == '1':
            from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit
            link = client.post(path+'/download-link', headers=owner)
            assert link.status_code == 200 and link.headers['cache-control'] == 'private, no-store'
            assert client.post(path+'/download-link', headers=other).status_code == 404
            assert client.post(path+'/download-link').status_code == 401
            signed = link.json()['url']; parsed = urlsplit(signed)
            assert parsed.hostname in ('localhost', '127.0.0.1'), 'Local S3 smoke must stay local'
            assert link.json()['expires_in_seconds'] == 5
            with httpx.Client(trust_env=False, timeout=30) as storage:
                assert storage.get(signed).content == response.content
                unsigned = urlunsplit(parsed._replace(query=''))
                assert storage.get(unsigned).status_code == 403
                assert storage.put(signed, content=b'cannot-overwrite').status_code == 403
                query = dict(parse_qsl(parsed.query)); query['X-Amz-Signature'] = '0'*64
                tampered = urlunsplit(parsed._replace(query=urlencode(query)))
                assert storage.get(tampered).status_code == 403
                time.sleep(6)
                assert storage.get(signed).status_code == 403
            (output_dir/'signed-storage-report.json').write_text(json.dumps({
                'private_get':'passed', 'anonymous_denied':True, 'write_denied':True,
                'tamper_denied':True, 'expiry_seconds':5, 'expired_denied':True})+'\n')
            print('Private signed download: anonymous/write/tamper/expiry controls passed')
        # Delete only this run's own synthetic project after saving its test evidence.
        assert client.delete(path,headers=other).status_code==404
        assert client.delete(path,headers=owner).status_code==202
        assert client.delete(path,headers=owner).status_code==202
        assert client.get(path,headers=owner).status_code==404
        assert client.get(path+'/download',headers=owner).status_code==404
        assert client.post(path+'/download-link',headers=owner).status_code==404
        assert all(row['id']!=job['id'] for row in client.get('/api/v1/jobs',headers=owner).json())
        assert client.post('/api/v1/jobs',headers={**owner,'Idempotency-Key':key},
            files={'file':('source.mp4',source.read_bytes(),'video/mp4')},
            data={**RIGHTS_FORM, **({'title':'Synthetic smoke test','style':'vlog','desired_seconds':'15'})}).status_code==410
        deletion={'accepted':True,'download_revoked':True,'replay_blocked':True}
        (output_dir/'deletion-report.json').write_text(json.dumps(deletion,indent=2)+'\n')
        print('Project deletion:',json.dumps(deletion))
    metadata = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(output)]))
    video = next(s for s in metadata['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in metadata['streams'] if s['codec_type'] == 'audio')
    assert (video['width'], video['height'], video['r_frame_rate']) == (1080, 1920, '30/1')
    assert video['codec_name'] == 'h264' and audio['codec_name'] == 'aac'
    assert 0 < float(metadata['format']['duration']) <= 5.0
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(output), '-f', 'null', '-'],
                   check=True, timeout=30)
    report = {'states_observed': states, 'width': 1080, 'height': 1920, 'fps': 30,
              'duration': float(metadata['format']['duration']),
              'elapsed_seconds': round(time.monotonic() - started, 2), 'owner_isolation': 'passed', 'upload_replay': 'passed'}
    (output_dir / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


def check_queued_cancellation(base_url, output_dir):
    source = output_dir / 'cancel-source.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi',
                    '-i', 'color=c=navy:s=160x90:r=15', '-t', '1', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', str(source)], check=True, timeout=30)
    with httpx.Client(base_url=base_url, trust_env=False, timeout=30) as client:
        registration = client.post('/api/v1/auth/register', json={
            'email': f'{uuid.uuid4()}@example.com', 'password': secrets.token_urlsafe(24)})
        assert registration.status_code == 201
        headers = {'Authorization': 'Bearer ' + registration.json()['access_token']}
        with source.open('rb') as handle:
            result = client.post('/api/v1/jobs', headers=headers,
                                 files={'file': ('source.mp4', handle, 'video/mp4')}, data=RIGHTS_FORM)
        assert result.status_code == 201
        path = '/api/v1/jobs/' + result.json()['id']
        cancelled = client.post(path + '/cancel', headers=headers)
        assert cancelled.status_code == 200 and cancelled.json()['status'] == 'cancelled'
        assert client.post(path + '/cancel', headers=headers).json()['status'] == 'cancelled'
        assert client.get(path + '/download', headers=headers).status_code == 409
    print('Queued cancellation over HTTP: passed')


def begin_resumable(base_url, output_dir):
    import hashlib
    import http.client
    from urllib.parse import urlsplit
    source = output_dir / 'resumable-source.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi',
        '-i', 'testsrc2=size=640x360:rate=30,noise=alls=30:allf=t', '-f', 'lavfi',
        '-i', 'sine=frequency=440:sample_rate=48000', '-t', '5', '-c:v', 'libx264',
        '-preset', 'ultrafast', '-crf', '0', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)],
        check=True, timeout=30)
    data = source.read_bytes()
    direct = os.getenv('NEXTPHASE_SMOKE_DIRECT') == '1'
    descriptor = dict(**RIGHTS_JSON,file_name='source.mp4', total_bytes=len(data), title='Resumable smoke', style='vlog', desired_seconds=15)
    if direct: descriptor['direct_upload'] = True
    with httpx.Client(base_url=base_url, trust_env=False, timeout=30) as client:
        response = client.post('/api/v1/auth/register', json={
            'email': f'{uuid.uuid4()}@example.com', 'password': secrets.token_urlsafe(24)})
        assert response.status_code == 201
        owner = {'Authorization': 'Bearer ' + response.json()['access_token']}
        key = uuid.uuid4().hex
        response = client.post('/api/v1/upload-sessions', headers={**owner, 'Idempotency-Key': key}, json=descriptor)
        assert response.status_code == 201, response.text
        session = response.json()
        usage=client.get('/api/v1/me/storage',headers=owner).json()
        assert usage['uninventoried_count']==0 and usage['known_reserved_bytes']>len(data)
        session['_storage_budget']=usage['known_reserved_bytes']
        assert session['rights_version']=='upload-rights-v1' and session['rights_confirmed_at']
        session['_rights_at']=session['rights_confirmed_at']
        size = session['chunk_bytes']
        assert len(data) > size*2, 'Synthetic source must span several chunks'
        first = data[:size]
        if direct:
            assert session['transfer_backend'] == 'direct-s3'
            response, first_grant = signed_chunk(client, owner, session, 0, first)
            with httpx.Client(trust_env=False, timeout=30) as storage:
                assert storage.put(first_grant['url'].replace('/incoming/','/sealed/'),
                    headers=first_grant['headers'], content=first).status_code == 403
                assert storage.put(first_grant['url'], headers={**first_grant['headers'],
                    'Content-Length':str(len(first)+1)}, content=first+b'!').status_code == 403
            # Try an altered payload through the still-live incoming capability.
            # Provider may reject its checksum; either way the sealed copy survives.
            with httpx.Client(trust_env=False, timeout=30) as storage:
                result = storage.put(first_grant['url'], headers=first_grant['headers'], content=b'X'*len(first))
                assert result.status_code in (200,400,403)
            next_chunk = data[size:size*2]
            second = client.post(f"/api/v1/upload-sessions/{session['id']}/part-url", headers=owner,
                json={'offset':size,'sha256':hashlib.sha256(next_chunk).hexdigest()}).json()
            time.sleep(6)
            with httpx.Client(trust_env=False, timeout=30) as storage:
                assert storage.put(second['url'], headers=second['headers'], content=next_chunk).status_code == 403
            renewed = client.post(f"/api/v1/upload-sessions/{session['id']}/part-url", headers=owner,
                json={'offset':size,'sha256':hashlib.sha256(next_chunk).hexdigest()}).json()
            assert renewed['grant_id'] == second['grant_id']
            session['_next_grant'] = renewed
        else:
            response = client.put(f"/api/v1/upload-sessions/{session['id']}/parts?offset=0",
                headers={**owner, 'X-Chunk-SHA256': hashlib.sha256(first).hexdigest()}, content=first)
        assert response.status_code == 200 and response.json()['received_bytes'] == size
    # Deliberately disconnect halfway through the NEXT chunk. It must not advance
    # the committed offset, even if the server dies before cleaning its staging file.
    address = urlsplit(session['_next_grant']['url'] if direct else base_url)
    connection_class = http.client.HTTPSConnection if address.scheme == 'https' else http.client.HTTPConnection
    connection = connection_class(address.hostname, address.port, timeout=10)
    next_chunk = data[size:size*2]
    target = address.path+'?'+address.query if direct else f"/api/v1/upload-sessions/{session['id']}/parts?offset={size}"
    connection.putrequest('PUT', target)
    headers = session['_next_grant']['headers'] if direct else {**owner, 'Content-Type':'application/octet-stream',
        'Content-Length':str(len(next_chunk)), 'X-Chunk-SHA256':hashlib.sha256(next_chunk).hexdigest()}
    for name, value in headers.items():
        connection.putheader(name, value)
    connection.endheaders()
    connection.send(next_chunk[:len(next_chunk)//2])
    connection.close()
    return owner, key, descriptor, session, data


def finish_resumable(base_url, output_dir, transfer, *, restarted):
    import hashlib
    owner, key, descriptor, session, data = transfer
    path = '/api/v1/upload-sessions/' + session['id']
    with httpx.Client(base_url=base_url, trust_env=False, timeout=60) as client:
        status = client.get(path, headers=owner).json()
        assert status['received_bytes'] == session['chunk_bytes'], status
        assert status['rights_version']=='upload-rights-v1' and status['rights_confirmed_at']==session['_rights_at']
        replay = client.post('/api/v1/upload-sessions', headers={**owner, 'Idempotency-Key': key}, json=descriptor)
        assert replay.status_code == 200 and replay.json()['id'] == session['id']
        for offset in range(status['received_bytes'], len(data), session['chunk_bytes']):
            chunk = data[offset:offset+session['chunk_bytes']]
            if status.get('transfer_backend') == 'direct-s3':
                response, _ = signed_chunk(client, owner, session, offset, chunk)
            else:
                response = client.put(path+f'/parts?offset={offset}',
                    headers={**owner, 'X-Chunk-SHA256': hashlib.sha256(chunk).hexdigest()}, content=chunk)
            assert response.status_code == 200, response.text
        response = client.post(path+'/complete', headers=owner)
        assert response.status_code == 200, response.text
        job_id = response.json()['id']
        assert client.post(path+'/complete', headers=owner).json()['id'] == job_id
        assert len(client.get('/api/v1/jobs', headers=owner).json()) == 1
        assert client.get('/api/v1/me/storage',headers=owner).json()['known_reserved_bytes']==session['_storage_budget']
        assert client.get(path, headers=owner).json()['source_sha256'] == hashlib.sha256(data).hexdigest()
        deadline = time.monotonic()+120
        while time.monotonic()<deadline:
            job = client.get('/api/v1/jobs/'+job_id, headers=owner).json()
            if job['status'] in ('succeeded','failed'): break
            time.sleep(.1)
        assert job['status']=='succeeded', job
        response = client.get('/api/v1/jobs/'+job_id+'/download', headers=owner)
        assert response.status_code==200
        output = output_dir/'resumable-output.mp4'
        output.write_bytes(response.content)
        if status.get('transfer_backend') == 'direct-s3':
            assert client.delete('/api/v1/jobs/'+job_id, headers=owner).status_code == 202
            assert client.post(path+'/part-url', headers=owner,
                json={'offset':0,'sha256':hashlib.sha256(data[:session['chunk_bytes']]).hexdigest()}).status_code == 410
    metadata = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output)]))
    video = next(s for s in metadata['streams'] if s['codec_type']=='video')
    assert (video['width'],video['height'],video['r_frame_rate'])==(1080,1920,'30/1')
    assert video['codec_name']=='h264' and any(s['codec_name']=='aac' for s in metadata['streams'])
    assert 0<float(metadata['format']['duration'])<=5
    subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(output),'-f','null','-'],check=True,timeout=30)
    report=dict(api_restarted=restarted, interrupted_part='not committed',
        transfer_backend=status.get('transfer_backend','api'),
        acknowledged_offset=session['chunk_bytes'], source_bytes=len(data),
        chunk_bytes=session['chunk_bytes'], checksum='passed', repeated_complete='one job', render_download='passed',rights_acknowledgement='preserved')
    if status.get('transfer_backend') == 'direct-s3':
        report.update(signed_expiry='passed', same_key_renewal='passed', sealed_overwrite_protection='passed')
    (output_dir/'resumable-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Resumable upload:',json.dumps(report))


def begin_auth(base_url):
    email=f'{uuid.uuid4()}@example.com';password=secrets.token_urlsafe(24)
    blocked=f'{uuid.uuid4()}@example.com'
    with httpx.Client(base_url=base_url,trust_env=False,timeout=30) as client:
        response=client.post('/api/v1/auth/register',json={'email':email,'password':password})
        assert response.status_code==201
        revoked=response.json()['access_token']
        active=client.post('/api/v1/auth/login',json={'email':email,'password':password}).json()['access_token']
        assert client.post('/api/v1/auth/logout',headers={'Authorization':'Bearer '+revoked}).status_code==204
        # Isolated smoke deliberately uses the documented default account budget.
        for _ in range(5):
            assert client.post('/api/v1/auth/login',json={'email':blocked,'password':'incorrect'}).status_code==401
    return email,password,revoked,active,blocked


def finish_auth(base_url, output_dir, state, restarted):
    email,password,revoked,active,blocked=state
    with httpx.Client(base_url=base_url,trust_env=False,timeout=30) as client:
        assert client.get('/api/v1/me',headers={'Authorization':'Bearer '+revoked}).status_code==401
        assert client.get('/api/v1/me',headers={'Authorization':'Bearer '+active}).status_code==200
        limited=client.post('/api/v1/auth/login',json={'email':blocked,'password':'incorrect'})
        assert limited.status_code==429 and int(limited.headers['retry-after'])>0
        replacement=secrets.token_urlsafe(24)
        assert client.post('/api/v1/auth/password',headers={'Authorization':'Bearer '+active},
            json={'current_password':password,'new_password':replacement}).status_code==204
        assert client.get('/api/v1/me',headers={'Authorization':'Bearer '+active}).status_code==401
        assert client.post('/api/v1/auth/login',json={'email':email,'password':password}).status_code==401
        new=client.post('/api/v1/auth/login',json={'email':email,'password':replacement})
        assert new.status_code==200
        bearer={'Authorization':'Bearer '+new.json()['access_token']}
        assert client.post('/api/v1/auth/logout-all',headers=bearer).status_code==204
        assert client.get('/api/v1/me',headers=bearer).status_code==401
    report={'api_restarted':restarted,'revocation':'passed','persisted_rate_limit':'passed',
            'password_change':'all sessions revoked','logout_all':'passed'}
    (output_dir/'auth-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Authentication:',json.dumps(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', help='Use an already running API and worker (creates synthetic test accounts/jobs).')
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.data' / ('smoke-' + uuid.uuid4().hex))
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    if args.base_url:
        auth_state = begin_auth(args.base_url)
        finish_auth(args.base_url, args.output_dir, auth_state, restarted=False)
        transfer = begin_resumable(args.base_url, args.output_dir)
        finish_resumable(args.base_url, args.output_dir, transfer, restarted=False)
        check_api(args.base_url, args.output_dir)
        return
    processes = []
    with tempfile.TemporaryDirectory(prefix='nextphase-smoke-') as temporary:
        env = os.environ.copy()
        env.update(APP_ENV='test',QUEUE_BACKEND='database',WORKER_REQUIRE_SANDBOX='false',WORKER_REQUIRE_LIMITS='false',AUTH_MAIL_BACKEND='disabled',AUTH_MAIL_SEND_ENABLED='false',AUTH_REQUIRE_VERIFIED_EMAIL='false',AUTH_MAIL_DIR=temporary+'/auth-mail', PYTHONPATH=str(ROOT / 'apps/api'),
                   DATABASE_URL='sqlite:///' + temporary + '/db.sqlite3', STORAGE_DIR=temporary + '/media',
                   JWT_SECRET=secrets.token_urlsafe(48), AI_PROVIDER='disabled', BILLING_PROVIDER='disabled',
                   WORKER_POLL_SECONDS='0.1', WORKER_HEARTBEAT_SECONDS='1', AUTH_LOGIN_ACCOUNT_LIMIT='5', AUTH_LOGIN_IP_LIMIT='30',
                   AUTH_REGISTER_IP_LIMIT='10', AUTH_PASSWORD_LIMIT='5', AUTH_WINDOW_SECONDS='900')
        broker_mode=os.getenv('NEXTPHASE_SMOKE_BROKER')=='1'
        if broker_mode:env['QUEUE_BACKEND']='valkey'
        subprocess.run([sys.executable, '-m', 'app.migrate'], cwd=ROOT, env=env, check=True, timeout=30)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        with (args.output_dir / 'api.log').open('w') as api_log, (args.output_dir / 'worker.log').open('w') as worker_log:
            try:
                processes.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
                                                   '--host', '127.0.0.1', '--port', str(port), '--no-proxy-headers'],
                                                  cwd=ROOT, env=env, stdout=api_log, stderr=subprocess.STDOUT))
                with httpx.Client(trust_env=False, timeout=1) as client:
                    for _ in range(100):
                        if processes[0].poll() is not None:
                            raise RuntimeError('API exited; inspect api.log')
                        try:
                            if client.get(base + '/health').status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        time.sleep(0.1)
                    else:
                        raise RuntimeError('API readiness timed out; inspect api.log')
                check_queued_cancellation(base, args.output_dir)
                auth_state = begin_auth(base)
                transfer = begin_resumable(base, args.output_dir)
                processes[0].kill()
                processes[0].wait(timeout=10)
                processes[0] = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
                    '--host', '127.0.0.1', '--port', str(port), '--no-proxy-headers'], cwd=ROOT, env=env,
                    stdout=api_log, stderr=subprocess.STDOUT)
                with httpx.Client(trust_env=False, timeout=1) as client:
                    for _ in range(100):
                        if processes[0].poll() is not None: raise RuntimeError('Restarted API exited; inspect api.log')
                        try:
                            if client.get(base+'/health').status_code == 200: break
                        except httpx.TransportError: pass
                        time.sleep(.1)
                    else: raise RuntimeError('Restarted API not ready')
                finish_auth(base, args.output_dir, auth_state, restarted=True)
                if broker_mode:
                    processes.append(subprocess.Popen([sys.executable,'-m','app.queue_supervisor'],cwd=ROOT,env=env,
                        stdout=worker_log,stderr=subprocess.STDOUT))
                processes.append(subprocess.Popen([sys.executable, '-m', 'app.worker'], cwd=ROOT, env=env,
                                                  stdout=worker_log, stderr=subprocess.STDOUT))
                finish_resumable(base, args.output_dir, transfer, restarted=True)
                check_api(base, args.output_dir)
                telemetry=json.loads(subprocess.check_output([sys.executable,'-m','app.telemetry'],cwd=ROOT,env=env,text=True))
                assert telemetry['attempt_states'].get('succeeded',0)>=2
                assert telemetry['attempt_wall_seconds']['samples']>=2
                assert telemetry['successful_output_bytes']>0
                assert telemetry['compute_estimate']['amount_for_observed_attempts'] is None
                (args.output_dir/'telemetry-report.json').write_text(json.dumps(telemetry,indent=2)+'\n')
                print('Render telemetry: measured successful attempts, output bytes and aggregate report passed')
                operations=json.loads(subprocess.check_output([sys.executable,'-m','app.operations','--check'],cwd=ROOT,env=env,text=True,timeout=30))
                assert operations['workers']['fresh']==1 and operations['status']=='ok'
                # S3 checks deliberately delete both successful projects. Current
                # queue state must be empty while retained attempts prove renders.
                assert operations['job_states'].get('queued',0)==0
                assert operations['job_states'].get('processing',0)==0
                assert operations['attempt_states_started_in_window'].get('succeeded',0)>=2
                (args.output_dir/'operations-live.json').write_text(json.dumps(operations,indent=2)+'\n')
                print('Operations: readiness, live worker and queue aggregates passed')
                subprocess.run([sys.executable,'-m','app.deletion'],cwd=ROOT,env=env,check=True,timeout=30)
                verification='from app.consent import RIGHTS_VERSION; from app.storage import usage; from app.db import SessionLocal; from app.models import RenderJob; from sqlalchemy import select; from pathlib import Path; from app.config import get_settings; db=SessionLocal(); rows=list(db.scalars(select(RenderJob).where(RenderJob.status=="deleted"))); assert rows and all(row.media_deleted_at is not None and usage(db,row.user_id)["known_reserved_bytes"]==0 and not (get_settings().storage_dir/row.user_id/row.id).exists() for row in rows); assert all(row.rights_version==RIGHTS_VERSION and row.rights_confirmed_at is not None for row in db.scalars(select(RenderJob))); db.close()'
                subprocess.run([sys.executable,'-c',verification],cwd=ROOT,env=env,check=True,timeout=30)
                if env.get('MEDIA_BACKEND') == 's3':
                    verification='from app.object_store import client,prefix,upload_prefix; from app.config import get_settings; from app.db import SessionLocal; from app.models import RenderJob,UploadSession; from sqlalchemy import select; db=SessionLocal(); rows=list(db.scalars(select(RenderJob).where(RenderJob.status=="deleted"))); assert rows and all(not client().list_objects_v2(Bucket=get_settings().s3_bucket,Prefix=prefix(row.user_id,row.id)).get("Contents") for row in rows); sessions=list(db.scalars(select(UploadSession).where(UploadSession.status=="deleted",UploadSession.transfer_backend=="direct-s3"))); assert all(not client().list_objects_v2(Bucket=get_settings().s3_bucket,Prefix=upload_prefix(row.user_id,row.id)).get("Contents") for row in sessions); db.close()'
                    subprocess.run([sys.executable,'-c',verification],cwd=ROOT,env=env,check=True,timeout=30)
                    print('Deleted original/output object-prefix removal: passed')
                print('Deleted source/output filesystem cleanup and storage release: passed')
            finally:
                for process in reversed(processes):
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        # Unknown-orphan cleanup is intentionally offline: stop only our own API
        # and worker first, then exercise it in the same disposable fixture DB.
        result=subprocess.check_output([sys.executable,str(ROOT/'scripts/retention_smoke.py')],
            cwd=ROOT,env=env,text=True,timeout=60)
        (args.output_dir/'retention-report.json').write_text(result)
        print('Offline retention:',result.strip())
        result=subprocess.check_output([sys.executable,str(ROOT/'scripts/operations_smoke.py'),str(args.output_dir)],cwd=ROOT,env=env,text=True,timeout=60)
        (args.output_dir/'operations-proof.json').write_text(result)
        print('Operations shutdown/failure detection:',result.strip())
    subprocess.run([sys.executable,str(ROOT/'scripts/smoke_account_deletion.py')],cwd=ROOT,check=True,timeout=120)
    subprocess.run([sys.executable,str(ROOT/'scripts/smoke_worker_recovery.py')],cwd=ROOT,check=True,timeout=120)
    subprocess.run([sys.executable,str(ROOT/'scripts/smoke_auth_recovery.py')],cwd=ROOT,check=True,timeout=120)
    subprocess.run([sys.executable,str(ROOT/'scripts/smoke_session_refresh.py')],cwd=ROOT,check=True,timeout=120)
    subprocess.run([sys.executable,str(ROOT/'scripts/smoke_email_delivery.py')],cwd=ROOT,check=True,timeout=120)
    print('Evidence:', args.output_dir)


if __name__ == '__main__':
    main()
