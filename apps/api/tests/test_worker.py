from datetime import timedelta

from app.db import SessionLocal
from app.models import RenderJob, utcnow
from app.worker import claim_job, mark_done, process, recover_stale_jobs, settings
from test_api import new_user


def queued_job(client, monkeypatch):
    monkeypatch.setattr('app.main.probe_video', lambda _: {'duration': 2, 'width': 320, 'height': 240})
    token = new_user(client)
    response = client.post('/api/v1/jobs', headers={'Authorization': f'Bearer {token}'},
                           files={'file': ('source.mp4', b'not-real-media', 'video/mp4')})
    assert response.status_code == 201
    return response.json()['id'], token


def test_worker_failure_is_terminal_and_private(client, monkeypatch):
    job_id, token = queued_job(client, monkeypatch)
    job = claim_job()
    assert job['id'] == job_id
    assert claim_job() is None
    process(job)  # Real ffmpeg rejects the malformed source.
    headers = {'Authorization': f'Bearer {token}'}
    result = client.get(f'/api/v1/jobs/{job_id}', headers=headers).json()
    assert result['status'] == 'failed'
    assert result['error_code'] == 'RENDER_FAILED'
    assert client.get(f'/api/v1/jobs/{job_id}/download', headers=headers).status_code == 409


def test_stale_worker_retries_are_bounded(client, monkeypatch):
    job_id, _ = queued_job(client, monkeypatch)
    assert claim_job()['id'] == job_id
    def make_stale():
        with SessionLocal.begin() as db:
            db.get(RenderJob, job_id).lease_expires_at = utcnow() - timedelta(days=1)
    make_stale()
    recover_stale_jobs()
    assert claim_job()['id'] == job_id
    make_stale()
    recover_stale_jobs()
    with SessionLocal() as db:
        job = db.get(RenderJob, job_id)
        assert job.status == 'failed'
        assert job.error_code == 'MAX_RETRIES'
        assert job.attempt_count == 2


def test_concurrent_processes_claim_each_job_once(client, monkeypatch, tmp_path):
    import json
    import os
    import subprocess
    import sys
    from sqlalchemy import select

    ids = {queued_job(client, monkeypatch)[0] for _ in range(12)}
    gate = tmp_path / 'start'
    code = '''
import json, sys, time
from pathlib import Path
from app.worker import claim_job
start = time.monotonic()
while not Path(sys.argv[1]).exists():
    if time.monotonic() - start > 10: raise RuntimeError('barrier timeout')
    time.sleep(0.01)
claims = []
for _ in range(32):
    job = claim_job()
    if job: claims.append(job)
print(json.dumps(claims))
'''
    processes = [subprocess.Popen([sys.executable, '-c', code, str(gate)], env=os.environ.copy(),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
    claims = []
    try:
        gate.touch()
        for process in processes:
            stdout, stderr = process.communicate(timeout=60)
            assert process.returncode == 0, stderr
            claims.extend(json.loads(stdout))
        assert len(claims) == len(ids)
        assert {job['id'] for job in claims} == ids
        assert len({job['claim_token'] for job in claims}) == len(ids)
        with SessionLocal() as db:
            jobs = db.scalars(select(RenderJob).where(RenderJob.id.in_(ids))).all()
            assert all(job.attempt_count == 1 and job.status == 'processing' for job in jobs)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
        for job in claims:
            mark_done(job['id'], job['claim_token'], error_code='TEST_CLEANUP')


def test_crashed_claim_can_retry_but_old_attempt_cannot_publish(client, monkeypatch):
    import json
    import os
    import subprocess
    import sys

    job_id, token = queued_job(client, monkeypatch)
    code = "import json,os; from app.worker import claim_job; print(json.dumps(claim_job()),flush=True); os._exit(7)"
    result = subprocess.run([sys.executable, '-c', code], env=os.environ.copy(), capture_output=True, text=True, timeout=30)
    assert result.returncode == 7
    old = json.loads(result.stdout)
    assert old['id'] == job_id
    assert recover_stale_jobs() == (0, 0)  # Unexpired lease is protected.
    with SessionLocal.begin() as db:
        db.get(RenderJob, job_id).lease_expires_at = utcnow() - timedelta(seconds=1)
    assert not mark_done(job_id, old['claim_token'], error_code='LATE_FAILURE')
    assert recover_stale_jobs() == (1, 0)
    retry = claim_job()
    assert retry['claim_token'] != old['claim_token']
    output = settings.storage_dir / retry['user_id'] / job_id / retry['claim_token'] / 'output.mp4'
    output.parent.mkdir(parents=True)
    output.write_bytes(b'winner')
    assert mark_done(job_id, retry['claim_token'], output_path=output, output_duration=1)
    assert not mark_done(job_id, old['claim_token'], error_code='LATE_FAILURE')
    def late_render(source, destination, duration, **kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b'loser')
        return {'duration': 1}
    monkeypatch.setattr('app.worker.render_baseline', late_render)
    process(old)
    assert output.read_bytes() == b'winner'
    assert not (output.parent.parent / old['claim_token'] / 'output.mp4').exists()
    headers = {'Authorization': f'Bearer {token}'}
    assert client.get(f'/api/v1/jobs/{job_id}/download', headers=headers).content == b'winner'
    with SessionLocal() as db:
        job = db.get(RenderJob, job_id)
        assert job.status == 'succeeded' and job.attempt_count == 2


def test_legacy_success_download_still_works(client, monkeypatch):
    job_id, token = queued_job(client, monkeypatch)
    with SessionLocal.begin() as db:
        job = db.get(RenderJob, job_id)
        output = settings.storage_dir / job.user_id / job_id / 'output.mp4'
        output.write_bytes(b'legacy-result')
        job.status = 'succeeded'
        job.output_path = str(output)
        job.output_duration_seconds = 2
        assert job.claim_token is None
    response = client.get(f'/api/v1/jobs/{job_id}/download', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 200
    assert response.content == b'legacy-result'
