from datetime import timedelta

from app.db import SessionLocal
from app.models import RenderJob, utcnow
from app.worker import claim_job, process, recover_stale_jobs
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
            db.get(RenderJob, job_id).started_at = utcnow() - timedelta(days=1)
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
