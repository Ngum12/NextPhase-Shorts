from upload_fixtures import RIGHTS_JSON
from upload_fixtures import RIGHTS_FORM
import hashlib
import io
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.main import settings
from app.models import RenderJob, UploadPart, UploadSession, utcnow
from app.uploads import part_directory, part_path
from test_api import new_user


@pytest.fixture
def context(client, monkeypatch):
    monkeypatch.setattr(settings, 'upload_chunk_bytes', 8)
    probe = lambda _: {'duration': 5, 'width': 320, 'height': 240}
    monkeypatch.setattr('app.uploads.probe_video', probe)
    monkeypatch.setattr('app.main.probe_video', probe)
    owner = {'Authorization': 'Bearer ' + new_user(client)}
    other = {'Authorization': 'Bearer ' + new_user(client)}
    owner_id = client.get('/api/v1/me', headers=owner).json()['id']
    yield owner, other, owner_id
    with SessionLocal.begin() as db:
        db.execute(update(RenderJob).where(RenderJob.user_id == owner_id,
            RenderJob.status.in_(('queued', 'processing'))).values(status='cancelled', claim_token=None, lease_expires_at=None))
        ids = list(db.scalars(select(UploadSession.id).where(UploadSession.user_id == owner_id)))
        db.execute(update(UploadSession).where(UploadSession.user_id == owner_id,
            UploadSession.status == 'uploading').values(status='aborted'))
    from app.uploads import cleanup_parts
    for session_id in ids:
        cleanup_parts(owner_id, session_id)


def create(client, owner, total=24, key=None, **values):
    return client.post('/api/v1/upload-sessions', headers={**owner, 'Idempotency-Key': key or uuid.uuid4().hex},
        json={**RIGHTS_JSON,'file_name': 'source.mp4', 'total_bytes': total, 'title': 'Resumable', 'style': 'vlog', 'desired_seconds': 15, **values})


def put(client, owner, session_id, offset, data, checksum=None):
    return client.put(f'/api/v1/upload-sessions/{session_id}/parts?offset={offset}',
        headers={**owner, 'X-Chunk-SHA256': checksum or hashlib.sha256(data).hexdigest()}, content=data)


def fill(client, owner, session_id, data):
    for offset in range(0, len(data), 8):
        response = put(client, owner, session_id, offset, data[offset:offset+8])
        assert response.status_code == 200, response.text


def test_session_key_is_replayable_immutable_and_owner_scoped(client, context):
    owner, other, _ = context
    key = uuid.uuid4().hex
    first = create(client, owner, key=key)
    assert first.status_code == 201
    assert first.json()['received_bytes'] == 0 and first.json()['chunk_bytes'] == 8
    assert first.json()['expires_at'].endswith('Z') or first.json()['expires_at'].endswith('+00:00')
    replay = create(client, owner, key=key)
    assert replay.status_code == 200 and replay.json()['id'] == first.json()['id']
    assert create(client, owner, key=key, title='Different').status_code == 409
    separate = create(client, other, key=key)
    assert separate.status_code == 201 and separate.json()['id'] != first.json()['id']
    client.post(f"/api/v1/upload-sessions/{separate.json()['id']}/abort", headers=other)


def test_upload_session_validation_and_owner_auth(client, context, monkeypatch):
    owner, other, _ = context
    assert create(client, owner, total=0).status_code == 422
    assert create(client, owner, desired_seconds=61).status_code == 422
    assert create(client, owner, file_name='evil.exe').status_code == 415
    assert create(client, owner, title='  ').status_code == 422
    assert create(client, owner, style='unknown').status_code == 422
    monkeypatch.setattr(settings, 'max_upload_bytes', 16)
    assert create(client, owner, total=24).status_code == 413
    session = create(client, owner, total=8).json()['id']
    assert client.get(f'/api/v1/upload-sessions/{session}').status_code == 401
    assert client.get(f'/api/v1/upload-sessions/{session}', headers=other).status_code == 404
    assert put(client, other, session, 0, b'12345678').status_code == 404
    for action in ('abort', 'complete'):
        assert client.post(f'/api/v1/upload-sessions/{session}/{action}', headers=other).status_code == 404


def test_parts_validate_integrity_boundaries_and_exact_replay(client, context):
    owner, _, owner_id = context
    session = create(client, owner).json()['id']
    assert put(client, owner, session, 0, b'123').status_code == 422
    assert put(client, owner, session, 0, b'123456789').status_code == 413
    assert put(client, owner, session, 0, b'12345678', '0'*64).status_code == 422
    assert put(client, owner, session, 1, b'12345678').status_code == 409
    assert put(client, owner, session, 8, b'12345678').status_code == 409
    first = put(client, owner, session, 0, b'12345678')
    assert first.status_code == 200 and first.json()['received_bytes'] == 8
    assert first.headers['Upload-Offset'] == '8'
    assert put(client, owner, session, 0, b'12345678').json()['received_bytes'] == 8
    assert put(client, owner, session, 0, b'abcdefgh').status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(UploadPart).where(UploadPart.session_id == session)) == 1
    assert not list(part_directory(owner_id, session).glob('*.staging'))
    assert client.post(f'/api/v1/upload-sessions/{session}/complete', headers=owner).status_code == 409


def test_lost_part_commit_ack_can_resume_without_advancing_twice(client, context, monkeypatch):
    owner, _, _ = context
    session = create(client, owner).json()['id']
    real_commit = Session.commit
    def lose_ack(db):
        real_commit(db)
        raise RuntimeError('lost part acknowledgement')
    with monkeypatch.context() as patch:
        patch.setattr(Session, 'commit', lose_ack)
        failed=put(client, owner, session, 0, b'12345678')
        assert failed.status_code==500 and 'lost part' not in failed.text
    assert client.get(f'/api/v1/upload-sessions/{session}', headers=owner).json()['received_bytes'] == 8
    assert put(client, owner, session, 0, b'12345678').json()['received_bytes'] == 8


def test_complete_is_repeat_safe_and_checks_stored_parts(client, context):
    from pathlib import Path
    owner, _, owner_id = context
    data = b'12345678abcdefghlastpart'
    session = create(client, owner, total=len(data)).json()['id']
    fill(client, owner, session, data)
    checksum = hashlib.sha256(data[:8]).hexdigest()
    part_path(owner_id, session, 0, checksum).write_bytes(b'corrupt!')
    assert client.post(f'/api/v1/upload-sessions/{session}/complete', headers=owner).status_code == 409
    assert put(client, owner, session, 0, data[:8]).status_code == 200  # Repair identical committed bytes.
    completed = client.post(f'/api/v1/upload-sessions/{session}/complete', headers=owner)
    assert completed.status_code == 200, completed.text
    job_id = completed.json()['id']
    assert client.post(f'/api/v1/upload-sessions/{session}/complete', headers=owner).json()['id'] == job_id
    snapshot = client.get(f'/api/v1/upload-sessions/{session}', headers=owner).json()
    assert snapshot['status'] == 'completed' and snapshot['source_sha256'] == hashlib.sha256(data).hexdigest()
    assert client.post(f'/api/v1/upload-sessions/{session}/abort', headers=owner).status_code == 409
    with SessionLocal() as db:
        job = db.get(RenderJob, job_id)
        assert Path(job.source_path).read_bytes() == data
        assert db.scalar(select(func.count()).select_from(RenderJob).where(RenderJob.user_id == owner_id)) == 1
    assert not part_directory(owner_id, session).exists()


def test_reservations_share_capacity_with_legacy_uploads_and_completion(client, context):
    owner, _, _ = context
    sessions = [create(client, owner).json()['id'] for _ in range(3)]
    assert create(client, owner).status_code == 429
    old = client.post('/api/v1/jobs', headers=owner, files={'file': ('source.mp4', io.BytesIO(b'fake'), 'video/mp4')}, data=RIGHTS_FORM)
    assert old.status_code == 429
    fill(client, owner, sessions[0], b'12345678abcdefghlastpart')
    assert client.post(f'/api/v1/upload-sessions/{sessions[0]}/complete', headers=owner).status_code == 200
    assert create(client, owner).status_code == 429  # Reservation became a queued job without double-counting.
    assert client.post(f'/api/v1/upload-sessions/{sessions[1]}/abort', headers=owner).status_code == 200
    assert create(client, owner).status_code == 201


def test_abort_and_expiry_release_capacity_and_clean_parts(client, context):
    from app.upload_cleanup import cleanup_uploads
    owner, _, owner_id = context
    session = create(client, owner).json()['id']
    put(client, owner, session, 0, b'12345678')
    assert client.post(f'/api/v1/upload-sessions/{session}/abort', headers=owner).json()['status'] == 'aborted'
    assert client.post(f'/api/v1/upload-sessions/{session}/abort', headers=owner).status_code == 200
    assert put(client, owner, session, 8, b'abcdefgh').status_code == 409
    assert not part_directory(owner_id, session).exists()
    expired = create(client, owner).json()['id']
    put(client, owner, expired, 0, b'12345678')
    with SessionLocal.begin() as db:
        db.get(UploadSession, expired).expires_at = utcnow()-timedelta(seconds=1)
    assert client.get(f'/api/v1/upload-sessions/{expired}', headers=owner).json()['status'] == 'expired'
    assert put(client, owner, expired, 8, b'abcdefgh').status_code == 410
    assert client.post(f'/api/v1/upload-sessions/{expired}/complete', headers=owner).status_code == 410
    cleanup_uploads()
    assert not part_directory(owner_id, expired).exists()
    with SessionLocal() as db:
        assert db.get(UploadSession, expired).parts_cleaned
        assert db.scalar(select(func.count()).select_from(UploadPart).where(UploadPart.session_id == expired)) == 0


def test_simultaneous_part_and_complete_requests_have_one_result(client, context):
    owner, _, owner_id = context
    key = uuid.uuid4().hex
    with ThreadPoolExecutor(max_workers=4) as pool:
        creations = list(pool.map(lambda _: create(client, owner, total=8, key=key), range(4)))
    assert sorted(result.status_code for result in creations) == [200, 200, 200, 201]
    assert len({result.json()['id'] for result in creations}) == 1
    session = creations[0].json()['id']
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: put(client, owner, session, 0, b'12345678'), range(4)))
    assert all(result.status_code == 200 and result.json()['received_bytes'] == 8 for result in results)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.post(f'/api/v1/upload-sessions/{session}/complete', headers=owner), range(4)))
    assert all(result.status_code == 200 for result in results), [result.text for result in results]
    assert len({result.json()['id'] for result in results}) == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(RenderJob).where(RenderJob.user_id == owner_id)) == 1


def test_slow_part_times_out_without_committing_bytes(client, context, monkeypatch):
    import asyncio
    from fastapi import HTTPException, Response
    from starlette.requests import Request
    from app.models import User
    from app.uploads import upload_part
    owner, _, owner_id = context
    session = create(client, owner, total=8).json()['id']
    monkeypatch.setattr(settings, 'upload_part_timeout_seconds', .01)
    async def receive():
        await asyncio.sleep(1)
        return {'type': 'http.request', 'body': b'12345678', 'more_body': False}
    request = Request({'type': 'http', 'method': 'PUT', 'path': '/'}, receive=receive)
    with SessionLocal() as db:
        user = db.get(User, owner_id)
        with pytest.raises(HTTPException) as error:
            asyncio.run(upload_part(session, request, Response(), offset=0,
                checksum=hashlib.sha256(b'12345678').hexdigest(), user=user, db=db))
        assert error.value.status_code == 408
    assert client.get(f'/api/v1/upload-sessions/{session}', headers=owner).json()['received_bytes'] == 0
    assert not list(part_directory(owner_id, session).glob('*.staging'))


def test_lost_completion_ack_keeps_source_and_returns_original_job(client, context, monkeypatch):
    from pathlib import Path
    owner, _, _ = context
    session = create(client, owner, total=8).json()['id']
    fill(client, owner, session, b'12345678')
    real_commit = Session.commit
    def lose_ack(db):
        real_commit(db)
        raise RuntimeError('lost completion acknowledgement')
    with monkeypatch.context() as patch:
        patch.setattr(Session, 'commit', lose_ack)
        failed=client.post(f'/api/v1/upload-sessions/{session}/complete', headers=owner)
        assert failed.status_code==500 and 'lost completion' not in failed.text
    snapshot = client.get(f'/api/v1/upload-sessions/{session}', headers=owner).json()
    assert snapshot['status'] == 'completed'
    replay = client.post(f'/api/v1/upload-sessions/{session}/complete', headers=owner)
    assert replay.status_code == 200 and replay.json()['id'] == snapshot['job_id']
    with SessionLocal() as db:
        assert Path(db.get(RenderJob, snapshot['job_id']).source_path).read_bytes() == b'12345678'


def test_parallel_session_and_legacy_admission_share_the_same_limit(client, context, monkeypatch):
    owner, _, owner_id = context
    monkeypatch.setattr(settings, 'max_active_jobs_per_user', 2)
    def submit(index):
        if index<2:
            return create(client, owner)
        return client.post('/api/v1/jobs', headers=owner, files={'file': ('source.mp4', b'fake', 'video/mp4')}, data=RIGHTS_FORM)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(submit, range(3)))
    assert sorted(result.status_code for result in results) == [201, 201, 429]
    from app.queue import active_count, reserved_upload_count
    with SessionLocal() as db:
        assert active_count(db, owner_id) + reserved_upload_count(db, owner_id) == 2


@pytest.mark.parametrize('invalid', ['not-video', 'too-long'])
def test_completion_validates_media_before_creating_job(client, context, monkeypatch, invalid):
    from app.media import MediaError
    owner, _, owner_id = context
    session = create(client, owner, total=8).json()['id']
    fill(client, owner, session, b'12345678')
    before = set(settings.storage_dir.rglob('input.*'))
    def probe(_):
        if invalid == 'not-video':
            raise MediaError('invalid')
        return {'duration': 600.1, 'width': 320, 'height': 240}
    monkeypatch.setattr('app.uploads.probe_video', probe)
    response = client.post(f'/api/v1/upload-sessions/{session}/complete', headers=owner)
    assert response.status_code == 422
    assert set(settings.storage_dir.rglob('input.*')) == before
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(RenderJob).where(RenderJob.user_id == owner_id)) == 0
    assert client.post(f'/api/v1/upload-sessions/{session}/abort', headers=owner).status_code == 200


def test_existing_reservation_can_complete_after_limit_is_lowered(client, context, monkeypatch):
    owner, _, owner_id = context
    sessions = [create(client, owner, total=8).json()['id'] for _ in range(3)]
    fill(client, owner, sessions[0], b'12345678')
    monkeypatch.setattr(settings, 'max_active_jobs_per_user', 1)
    response = client.post(f'/api/v1/upload-sessions/{sessions[0]}/complete', headers=owner)
    assert response.status_code == 200
    assert create(client, owner, total=8).status_code == 429
    from app.queue import active_count, reserved_upload_count
    with SessionLocal() as db:
        assert active_count(db, owner_id) + reserved_upload_count(db, owner_id) == 3
