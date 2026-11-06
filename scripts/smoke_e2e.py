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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', help='Use an already running API and worker (creates synthetic test accounts/jobs).')
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.data' / ('smoke-' + uuid.uuid4().hex))
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    if args.base_url:
        check_api(args.base_url, args.output_dir)
        return
    processes = []
    with tempfile.TemporaryDirectory(prefix='nextphase-smoke-') as temporary:
        env = os.environ.copy()
        env.update(APP_ENV='test', PYTHONPATH=str(ROOT / 'apps/api'),
                   DATABASE_URL='sqlite:///' + temporary + '/db.sqlite3', STORAGE_DIR=temporary + '/media',
                   JWT_SECRET=secrets.token_urlsafe(48), AI_PROVIDER='disabled', BILLING_PROVIDER='disabled',
                   WORKER_POLL_SECONDS='0.1')
        subprocess.run([sys.executable, '-m', 'app.migrate'], cwd=ROOT, env=env, check=True, timeout=30)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        with (args.output_dir / 'api.log').open('w') as api_log, (args.output_dir / 'worker.log').open('w') as worker_log:
            try:
                processes.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
                                                   '--host', '127.0.0.1', '--port', str(port)],
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
                processes.append(subprocess.Popen([sys.executable, '-m', 'app.worker'], cwd=ROOT, env=env,
                                                  stdout=worker_log, stderr=subprocess.STDOUT))
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
