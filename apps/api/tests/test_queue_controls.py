import io
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from app.db import SessionLocal
from app.main import settings
from app.models import RenderJob
from app.worker import claim_job, mark_done, process, recover_stale_jobs
from test_api import new_user


def headers(client):
    return {'Authorization': 'Bearer ' + new_user(client)}


def upload(client, owner, key=None, content=b'synthetic', **data):
    return client.post('/api/v1/jobs', headers={**owner, **({'Idempotency-Key': key} if key else {})},
        files={'file': ('source.mp4', io.BytesIO(content), 'video/mp4')},
        data={'title': 'Queue test', 'style': 'vlog', 'desired_seconds': '15', **data})


@pytest.fixture
def valid_probe(monkeypatch):
    monkeypatch.setattr('app.main.probe_video', lambda _: {'duration': 5, 'width': 320, 'height': 240})


def cancel(client, owner, job_id):
    return client.post(f'/api/v1/jobs/{job_id}/cancel', headers=owner)


def test_replay_and_conflict_do_not_duplicate_media(client, valid_probe):
    owner = headers(client)
    key = uuid.uuid4().hex
    first = upload(client, owner, key)
    assert first.status_code == 201
    job_id = first.json()['id']
    before = set(settings.storage_dir.rglob('input.*'))
    replay = upload(client, owner, key)
    assert replay.status_code == 200
    assert replay.headers['Idempotency-Replayed'] == 'true'
    assert replay.json()['id'] == job_id
    assert upload(client, owner, key, content=b'changed').status_code == 409
    assert upload(client, owner, key, title='Changed settings').status_code == 409
    assert set(settings.storage_dir.rglob('input.*')) == before
    # Keys are owner scoped, not global; cancellation stays sticky on replay.
    other = headers(client)
    separate = upload(client, other, key)
    assert separate.status_code == 201 and separate.json()['id'] != job_id
    assert cancel(client, owner, job_id).status_code == 200
    assert upload(client, owner, key).json()['status'] == 'cancelled'
    assert cancel(client, other, separate.json()['id']).status_code == 200


def test_active_limit_replay_and_cancellation_release_capacity(client, valid_probe, monkeypatch):
    monkeypatch.setattr(settings, 'max_active_jobs_per_user', 2)
    owner, other = headers(client), headers(client)
    key = uuid.uuid4().hex
    first = upload(client, owner, key).json()['id']
    second = upload(client, owner).json()['id']
    before = set(settings.storage_dir.rglob('input.*'))
    full = upload(client, owner)
    assert full.status_code == 429 and full.headers['Retry-After'] == '5'
    assert set(settings.storage_dir.rglob('input.*')) == before
    assert upload(client, owner, key).json()['id'] == first
    assert cancel(client, other, first).status_code == 404
    assert client.post(f'/api/v1/jobs/{first}/cancel').status_code == 401
    result = cancel(client, owner, first)
    assert result.json()['status'] == 'cancelled'
    assert result.json()['finished_at']
    assert cancel(client, owner, first).json()['finished_at'] == result.json()['finished_at']
    assert client.get(f'/api/v1/jobs/{first}/download', headers=owner).status_code == 409
    replacement = upload(client, owner)
    assert replacement.status_code == 201
    cancel(client, owner, second)
    cancel(client, owner, replacement.json()['id'])


def test_cancel_processing_fences_completion_and_recovery(client, valid_probe):
    owner = headers(client)
    job_id = upload(client, owner).json()['id']
    attempt = claim_job()
    assert attempt['id'] == job_id
    assert cancel(client, owner, job_id).json()['status'] == 'cancelled'
    assert not mark_done(job_id, attempt['claim_token'], error_code='LATE_FAILURE')
    process(attempt)  # Ownership callback cancels before spawning FFmpeg.
    assert recover_stale_jobs() == (0, 0)
    assert client.get(f'/api/v1/jobs/{job_id}', headers=owner).json()['status'] == 'cancelled'
    assert not list((settings.storage_dir / attempt['user_id'] / job_id).rglob('output*.mp4'))


def test_terminal_success_cannot_be_cancelled(client, valid_probe):
    owner = headers(client)
    job_id = upload(client, owner).json()['id']
    attempt = claim_job()
    assert mark_done(job_id, attempt['claim_token'], output_path='unused', output_duration=1)
    assert cancel(client, owner, job_id).status_code == 409
    assert client.get(f'/api/v1/jobs/{job_id}', headers=owner).json()['status'] == 'succeeded'


def test_processing_limit_does_not_block_another_owner(client, valid_probe):
    owner, other = headers(client), headers(client)
    first = upload(client, owner).json()['id']
    second = upload(client, owner).json()['id']
    third = upload(client, other).json()['id']
    assert claim_job()['id'] == first
    assert claim_job()['id'] == third  # Oldest owner's next job waits at capacity.
    assert claim_job() is None
    cancel(client, owner, first)
    assert claim_job()['id'] == second
    cancel(client, owner, second)
    cancel(client, other, third)


@pytest.mark.parametrize('same_key', [True, False])
def test_parallel_admission_serializes_keys_and_capacity(client, tmp_path, same_key):
    owner = headers(client)
    owner_id = client.get('/api/v1/me', headers=owner).json()['id']
    gate = tmp_path / 'go'
    shared_key = uuid.uuid4().hex
    code = '''
import json, sys, time, uuid
from pathlib import Path
from fastapi import HTTPException
from app.db import SessionLocal
from app.models import RenderJob
from app.queue import admit_job
start=time.monotonic()
while not Path(sys.argv[1]).exists():
    if time.monotonic()-start>10: raise RuntimeError('barrier timeout')
    time.sleep(.01)
with SessionLocal.begin() as db:
    job=RenderJob(id=str(uuid.uuid4()), user_id=sys.argv[2],title='Parallel',style='vlog',
        desired_seconds=15,source_duration_seconds=5,source_path='synthetic',status='queued',storage_reserved_bytes=1,max_render_bytes=67108864,
        idempotency_key=sys.argv[3],request_hash='a'*64)
    try:
        admitted,replayed=admit_job(db,job)
        print(json.dumps({'id':admitted.id,'status':200 if replayed else 201}),flush=True)
    except HTTPException as error:
        print(json.dumps({'status':error.status_code}),flush=True)
'''
    processes = [subprocess.Popen([sys.executable, '-c', code, str(gate), owner_id,
                  shared_key if same_key else uuid.uuid4().hex], env=os.environ.copy(),
                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
    results = []
    try:
        gate.touch()
        for child in processes:
            stdout, stderr = child.communicate(timeout=60)
            assert child.returncode == 0, stderr
            results.append(json.loads(stdout))
        assert sorted(r['status'] for r in results) == ([200, 200, 200, 201] if same_key else [201, 201, 201, 429])
        with SessionLocal() as db:
            jobs = db.scalars(select(RenderJob).where(RenderJob.user_id == owner_id)).all()
            assert len(jobs) == (1 if same_key else 3)
        assert len({r['id'] for r in results if 'id' in r}) == len(jobs)
    finally:
        for child in processes:
            if child.poll() is None:
                child.kill()
                child.wait()
        for job in client.get('/api/v1/jobs', headers=owner).json():
            cancel(client, owner, job['id'])


def test_idempotency_key_validation(client, valid_probe):
    owner = headers(client)
    assert upload(client, owner, 'short').status_code == 422
    assert upload(client, owner, 'invalid key').status_code == 422
    assert upload(client, owner, 'a' * 129).status_code == 422


def test_parallel_claimants_respect_one_processing_job_per_owner(client, valid_probe, tmp_path):
    owner = headers(client)
    ids = {upload(client, owner).json()['id'] for _ in range(3)}
    gate = tmp_path / 'claim-go'
    code = '''
import json,sys,time
from pathlib import Path
from app.worker import claim_job
start=time.monotonic()
while not Path(sys.argv[1]).exists():
    if time.monotonic()-start>10: raise RuntimeError('barrier timeout')
    time.sleep(.01)
claims=[]
for _ in range(8):
    job=claim_job()
    if job: claims.append(job['id'])
print(json.dumps(claims))
'''
    children = [subprocess.Popen([sys.executable, '-c', code, str(gate)], env=os.environ.copy(),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
    try:
        gate.touch()
        claimed = []
        for child in children:
            stdout, stderr = child.communicate(timeout=60)
            assert child.returncode == 0, stderr
            claimed.extend(json.loads(stdout))
        assert len(claimed) == 1 and claimed[0] in ids
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait()
        for job_id in ids:
            cancel(client, owner, job_id)


def test_lost_commit_ack_retains_accepted_source_and_replays(client, valid_probe, monkeypatch):
    from sqlalchemy.orm import Session
    owner = headers(client)
    key = uuid.uuid4().hex
    real_commit = Session.commit
    def lose_ack(session):
        real_commit(session)
        raise RuntimeError('simulated lost commit acknowledgement')
    with monkeypatch.context() as patch:
        patch.setattr(Session, 'commit', lose_ack)
        with pytest.raises(RuntimeError, match='lost commit'):
            upload(client, owner, key)
    jobs = client.get('/api/v1/jobs', headers=owner).json()
    assert len(jobs) == 1
    with SessionLocal() as db:
        accepted = db.get(RenderJob, jobs[0]['id'])
        assert Path(accepted.source_path).read_bytes() == b'synthetic'
    replay = upload(client, owner, key)
    assert replay.status_code == 200 and replay.json()['id'] == jobs[0]['id']
    cancel(client, owner, jobs[0]['id'])
