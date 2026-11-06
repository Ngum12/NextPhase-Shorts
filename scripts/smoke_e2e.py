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
        assert client.get('/api/v1/jobs').status_code == 401
        assert all(not style['available'] for style in client.get('/api/v1/styles').json())
        def register():
            response = client.post('/api/v1/auth/register', json={
                'email': f'{uuid.uuid4()}@example.com', 'password': secrets.token_urlsafe(24)})
            assert response.status_code == 201, response.status_code
            return {'Authorization': 'Bearer ' + response.json()['access_token']}
        owner, other = register(), register()
        key = uuid.uuid4().hex
        with source.open('rb') as handle:
            response = client.post('/api/v1/jobs', headers={**owner, 'Idempotency-Key': key},
                                   files={'file': ('source.mp4', handle, 'video/mp4')},
                                   data={'title': 'Synthetic smoke test', 'style': 'vlog', 'desired_seconds': '15'})
        assert response.status_code == 201, response.status_code
        job = response.json()
        assert job['status'] == 'queued'
        path = '/api/v1/jobs/' + job['id']
        with source.open('rb') as handle:
            replay = client.post('/api/v1/jobs', headers={**owner, 'Idempotency-Key': key},
                files={'file': ('source.mp4', handle, 'video/mp4')},
                data={'title': 'Synthetic smoke test', 'style': 'vlog', 'desired_seconds': '15'})
        assert replay.status_code == 200 and replay.json()['id'] == job['id']
        assert replay.headers['Idempotency-Replayed'] == 'true'
        assert len(client.get('/api/v1/jobs', headers=owner).json()) == 1
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
        output = output_dir / 'output.mp4'
        output.write_bytes(response.content)
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
                                 files={'file': ('source.mp4', handle, 'video/mp4')})
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
    descriptor = dict(file_name='source.mp4', total_bytes=len(data), title='Resumable smoke', style='vlog', desired_seconds=15)
    with httpx.Client(base_url=base_url, trust_env=False, timeout=30) as client:
        response = client.post('/api/v1/auth/register', json={
            'email': f'{uuid.uuid4()}@example.com', 'password': secrets.token_urlsafe(24)})
        assert response.status_code == 201
        owner = {'Authorization': 'Bearer ' + response.json()['access_token']}
        key = uuid.uuid4().hex
        response = client.post('/api/v1/upload-sessions', headers={**owner, 'Idempotency-Key': key}, json=descriptor)
        assert response.status_code == 201, response.text
        session = response.json()
        size = session['chunk_bytes']
        assert len(data) > size*2, 'Synthetic source must span several chunks'
        first = data[:size]
        response = client.put(f"/api/v1/upload-sessions/{session['id']}/parts?offset=0",
            headers={**owner, 'X-Chunk-SHA256': hashlib.sha256(first).hexdigest()}, content=first)
        assert response.status_code == 200 and response.json()['received_bytes'] == size
    # Deliberately disconnect halfway through the NEXT chunk. It must not advance
    # the committed offset, even if the server dies before cleaning its staging file.
    address = urlsplit(base_url)
    connection_class = http.client.HTTPSConnection if address.scheme == 'https' else http.client.HTTPConnection
    connection = connection_class(address.hostname, address.port, timeout=10)
    next_chunk = data[size:size*2]
    connection.putrequest('PUT', f"/api/v1/upload-sessions/{session['id']}/parts?offset={size}")
    for name, value in {**owner, 'Content-Type': 'application/octet-stream', 'Content-Length': str(len(next_chunk)),
                        'X-Chunk-SHA256': hashlib.sha256(next_chunk).hexdigest()}.items():
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
        replay = client.post('/api/v1/upload-sessions', headers={**owner, 'Idempotency-Key': key}, json=descriptor)
        assert replay.status_code == 200 and replay.json()['id'] == session['id']
        for offset in range(status['received_bytes'], len(data), session['chunk_bytes']):
            chunk = data[offset:offset+session['chunk_bytes']]
            response = client.put(path+f'/parts?offset={offset}',
                headers={**owner, 'X-Chunk-SHA256': hashlib.sha256(chunk).hexdigest()}, content=chunk)
            assert response.status_code == 200, response.text
        response = client.post(path+'/complete', headers=owner)
        assert response.status_code == 200, response.text
        job_id = response.json()['id']
        assert client.post(path+'/complete', headers=owner).json()['id'] == job_id
        assert len(client.get('/api/v1/jobs', headers=owner).json()) == 1
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
    metadata = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output)]))
    video = next(s for s in metadata['streams'] if s['codec_type']=='video')
    assert (video['width'],video['height'],video['r_frame_rate'])==(1080,1920,'30/1')
    assert video['codec_name']=='h264' and any(s['codec_name']=='aac' for s in metadata['streams'])
    assert 0<float(metadata['format']['duration'])<=5
    subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(output),'-f','null','-'],check=True,timeout=30)
    report=dict(api_restarted=restarted, interrupted_part='not committed',
        acknowledged_offset=session['chunk_bytes'], source_bytes=len(data),
        chunk_bytes=session['chunk_bytes'], checksum='passed', repeated_complete='one job', render_download='passed')
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
        env.update(APP_ENV='test', PYTHONPATH=str(ROOT / 'apps/api'),
                   DATABASE_URL='sqlite:///' + temporary + '/db.sqlite3', STORAGE_DIR=temporary + '/media',
                   JWT_SECRET=secrets.token_urlsafe(48), AI_PROVIDER='disabled', BILLING_PROVIDER='disabled',
                   WORKER_POLL_SECONDS='0.1', AUTH_LOGIN_ACCOUNT_LIMIT='5', AUTH_LOGIN_IP_LIMIT='30',
                   AUTH_REGISTER_IP_LIMIT='10', AUTH_PASSWORD_LIMIT='5', AUTH_WINDOW_SECONDS='900')
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
                processes.append(subprocess.Popen([sys.executable, '-m', 'app.worker'], cwd=ROOT, env=env,
                                                  stdout=worker_log, stderr=subprocess.STDOUT))
                finish_resumable(base, args.output_dir, transfer, restarted=True)
                check_api(base, args.output_dir)
            finally:
                for process in reversed(processes):
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    print('Evidence:', args.output_dir)


if __name__ == '__main__':
    main()
