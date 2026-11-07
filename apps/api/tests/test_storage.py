from upload_fixtures import RIGHTS_FORM
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,update
from app.db import SessionLocal
from app.models import RenderJob,UploadSession,utcnow
from app.storage import reservation,reconcile
from app.worker import settings
from app.deletion import cleanup_deleted
from app.upload_cleanup import cleanup_uploads
from test_api import new_user
from test_upload_sessions import create,fill,context


def legacy(client,owner,key=None,data=b'abcdefghijklmnopqrstuvwx'):
    return client.post('/api/v1/jobs',headers={**owner,**({'Idempotency-Key':key} if key else {})},files={'file':('source.mp4',data,'video/mp4')}, data=RIGHTS_FORM)


def budget(client,owner):return client.get('/api/v1/me/storage',headers=owner).json()


def test_legacy_admission_replay_owner_isolation_and_cleanup_release(client,context,monkeypatch):
    owner,other,owner_id=context;amount=reservation(24,settings.max_render_bytes)
    monkeypatch.setattr(settings,'account_storage_bytes',amount)
    key=uuid.uuid4().hex
    first=legacy(client,owner,key);assert first.status_code==201
    job_id=first.json()['id']
    assert budget(client,owner)['known_reserved_bytes']==amount
    assert legacy(client,owner,key).status_code==200
    assert legacy(client,owner).status_code==409
    assert budget(client,other)['known_reserved_bytes']==0
    assert client.get('/api/v1/me/storage').status_code==401
    assert client.delete('/api/v1/jobs/'+job_id,headers=owner).status_code==202
    assert budget(client,owner)['available_bytes']==0
    cleanup_deleted()
    assert budget(client,owner)['available_bytes']==amount
    assert legacy(client,owner).status_code==201


def test_resumable_reservation_transfers_once_and_honors_old_budget(client,context,monkeypatch):
    owner,_,_=context;amount=reservation(24,settings.max_render_bytes);old_cap=settings.max_render_bytes
    monkeypatch.setattr(settings,'account_storage_bytes',amount)
    key=uuid.uuid4().hex;session=create(client,owner,total=24,key=key).json();sid=session['id']
    assert create(client,owner,total=24).status_code==409
    assert create(client,owner,total=24,key=key).status_code==200
    fill(client,owner,sid,b'abcdefghijklmnopqrstuvwx')
    monkeypatch.setattr(settings,'account_storage_bytes',1)
    monkeypatch.setattr(settings,'max_render_bytes',1048576)
    complete=client.post(f'/api/v1/upload-sessions/{sid}/complete',headers=owner)
    assert complete.status_code==200
    assert client.post(f'/api/v1/upload-sessions/{sid}/complete',headers=owner).json()['id']==complete.json()['id']
    assert budget(client,owner)['known_reserved_bytes']==amount
    with SessionLocal() as db:assert db.get(RenderJob,complete.json()['id']).max_render_bytes==old_cap


def test_abort_and_expiry_keep_budget_until_staging_cleanup(client,context,monkeypatch):
    from datetime import timedelta
    owner,_,_=context;amount=reservation(24,settings.max_render_bytes)
    monkeypatch.setattr(settings,'account_storage_bytes',amount)
    for expired in (False,True):
        sid=create(client,owner,total=24).json()['id']
        if expired:
            with SessionLocal.begin() as db:db.get(UploadSession,sid).expires_at=utcnow()-timedelta(seconds=1)
        else:assert client.post(f'/api/v1/upload-sessions/{sid}/abort',headers=owner).status_code==200
        assert create(client,owner,total=24).status_code==409
        cleanup_uploads()
        assert budget(client,owner)['available_bytes']==amount


def test_unknown_legacy_inventory_blocks_new_uploads_until_reconciled(client,context):
    owner,_,_=context
    job_id=legacy(client,owner).json()['id']
    with SessionLocal.begin() as db:
        row=db.get(RenderJob,job_id);row.storage_reserved_bytes=None;row.max_render_bytes=None
        row.source_path='/never-trust-this-outside-path/input.mp4'
    assert budget(client,owner)['uninventoried_count']==1
    assert legacy(client,owner).status_code==409
    reconcile()
    assert budget(client,owner)['uninventoried_count']==0
    assert legacy(client,owner).status_code==201


def test_missing_inventory_does_not_guess_zero(client,context):
    import shutil
    owner,_,owner_id=context;job_id=legacy(client,owner).json()['id']
    with SessionLocal.begin() as db:db.get(RenderJob,job_id).storage_reserved_bytes=None
    shutil.rmtree(settings.storage_dir/owner_id/job_id)
    _,missing=reconcile();assert missing>=1
    assert budget(client,owner)['uninventoried_count']==1
    assert legacy(client,owner).status_code==409
    client.delete('/api/v1/jobs/'+job_id,headers=owner);cleanup_deleted()
    assert budget(client,owner)['uninventoried_count']==0


def test_simultaneous_legacy_requests_cannot_overbook_storage(client,context,monkeypatch):
    owner,_,_=context
    monkeypatch.setattr(settings,'account_storage_bytes',reservation(24,settings.max_render_bytes))
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:legacy(client,owner).status_code,range(4)))
    assert sorted(results)==[201,409,409,409]


def test_inventory_rejects_unsafe_or_noncanonical_paths(context,monkeypatch):
    from app.storage import measured_tree
    from pathlib import Path
    _,_,owner_id=context
    with pytest.raises(ValueError):measured_tree(owner_id,'../outside')
    monkeypatch.setattr(Path,'is_symlink',lambda self:True)
    with pytest.raises(ValueError):measured_tree(owner_id,str(uuid.uuid4()))


def test_inventory_permission_errors_remain_unknown(client,context,monkeypatch):
    import app.storage as storage
    owner,_,_=context;job_id=legacy(client,owner).json()['id']
    with SessionLocal.begin() as db:db.get(RenderJob,job_id).storage_reserved_bytes=None
    def denied(*args,**kwargs):kwargs['onerror'](PermissionError('private path'))
    monkeypatch.setattr(storage.os,'walk',denied)
    _,missing=reconcile();assert missing>=1
    assert budget(client,owner)['uninventoried_count']==1
