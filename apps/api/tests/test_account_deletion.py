"""Account-wide access revocation and durable owner-scoped cleanup."""
from datetime import timedelta
import uuid
import pytest
from sqlalchemy import select
from app.db import SessionLocal
from app.models import User,AuthSession,AccountDeletion,RenderJob,utcnow
from app.account_deletion import cleanup_accounts,receipt_hash
from app.queue import lock_owner
from app.worker import claim_job,mark_done,settings
from test_api import new_user
from test_worker import queued_job
from test_object_store import remote
from test_upload_sessions import context

PASSWORD='correct horse battery staple'
def headers(token):return {'Authorization':'Bearer '+token}
def request(client,token,key=None,password=PASSWORD):
    return client.post('/api/v1/account/delete',headers=headers(token),json={'current_password':password,'receipt_key':key or str(uuid.uuid4())})
def receipt(client,key):return client.post('/api/v1/account/deletion-receipt',json={'receipt_key':key})
def due(uid):
    with SessionLocal.begin() as db:db.get(AccountDeletion,uid).cleanup_after=utcnow()-timedelta(seconds=1)


def test_disable_revokes_every_session_and_claim_preserves_other_account(client,monkeypatch):
    jid,token=queued_job(client,monkeypatch);other=new_user(client);claimed=claim_job()
    with SessionLocal() as db:
        uid=db.get(RenderJob,jid).user_id;email=db.get(User,uid).email
    second=client.post('/api/v1/auth/login',json={'email':email,'password':PASSWORD}).json()['access_token']
    key=str(uuid.uuid4());response=request(client,token,key)
    assert response.status_code==202 and response.json()=={'status':'account_disabled','media_cleanup':'scheduled'}
    assert response.headers['cache-control']=='private, no-store'
    for access in (token,second):
        assert client.get('/api/v1/me',headers=headers(access)).status_code==401
        assert client.get(f'/api/v1/jobs/{jid}/download',headers=headers(access)).status_code==401
    assert client.post('/api/v1/auth/login',json={'email':email,'password':PASSWORD}).status_code==401
    assert not mark_done(jid,claimed['claim_token'],error_code='LATE')
    assert client.get('/api/v1/me',headers=headers(other)).status_code==200
    assert receipt(client,key).json()==response.json()
    with SessionLocal() as db:
        user=db.get(User,uid);assert user.deleted_at and user.email=='!deleted:'+uid and user.password_hash=='!disabled'
        assert all(s.revoked_at for s in db.scalars(select(AuthSession).where(AuthSession.user_id==uid)))
        job=db.get(RenderJob,jid);assert job.status=='deleted' and not job.source_path and not job.output_path
        row=db.get(AccountDeletion,uid);assert row.receipt_hash==receipt_hash(key) and row.receipt_hash!=key
        with pytest.raises(Exception) as failure:lock_owner(db,uid)
        assert failure.value.status_code==401
    fresh=client.post('/api/v1/auth/register',json={'email':email,'password':PASSWORD});assert fresh.status_code==201
    assert client.get('/api/v1/jobs',headers=headers(fresh.json()['access_token'])).json()==[]


def test_wrong_password_and_receipt_unknown_expired_or_invalid(client):
    token=new_user(client);key=str(uuid.uuid4())
    assert request(client,token,key,'wrong').status_code==400
    assert client.get('/api/v1/me',headers=headers(token)).status_code==200
    assert receipt(client,key).status_code==404
    assert receipt(client,'invalid').status_code==422
    assert request(client,token,key).status_code==202
    assert request(client,token,key).status_code==401
    with SessionLocal.begin() as db:
        row=db.scalar(select(AccountDeletion).where(AccountDeletion.receipt_hash==receipt_hash(key)))
        row.receipt_expires_at=utcnow()-timedelta(seconds=1)
    assert receipt(client,key).status_code==404


def test_cleanup_waits_retries_and_resweeps_only_disabled_owner(client,monkeypatch,caplog):
    jid,token=queued_job(client,monkeypatch)
    with SessionLocal() as db:uid=db.get(RenderJob,jid).user_id
    root=settings.storage_dir/uid;assert root.exists()
    other=settings.storage_dir/str(uuid.uuid4());other.mkdir();(other/'keep').write_bytes(b'keep')
    key=str(uuid.uuid4());assert request(client,token,key).status_code==202
    cleanup_accounts();assert root.exists()
    due(uid)
    import app.account_deletion as deletion
    original=deletion.remove_owner_tree
    def failure(_):raise PermissionError('private-path-do-not-log')
    monkeypatch.setattr(deletion,'remove_owner_tree',failure);cleanup_accounts()
    assert 'private-path-do-not-log' not in caplog.text
    assert receipt(client,key).json()['media_cleanup']=='scheduled'
    monkeypatch.setattr(deletion,'remove_owner_tree',original);cleanup_accounts()
    assert not root.exists() and (other/'keep').exists()
    assert receipt(client,key).json()['media_cleanup']=='verified'
    root.mkdir();(root/'late').write_bytes(b'late');cleanup_accounts();assert not root.exists()


def test_cleanup_namespace_failure_and_remote_prefix_scope(client,monkeypatch,remote):
    jid,token=queued_job(client,monkeypatch)
    with SessionLocal() as db:uid=db.get(RenderJob,jid).user_id
    remote.objects[f'uploads/{uid}/orphan/incoming']=(b'private',{})
    remote.objects['media/other-owner/keep']=(b'keep',{})
    key=str(uuid.uuid4());assert request(client,token,key).status_code==202;due(uid)
    endpoint=settings.s3_endpoint;monkeypatch.setattr(settings,'s3_endpoint','http://localhost:9999')
    cleanup_accounts();assert receipt(client,key).json()['media_cleanup']=='scheduled'
    monkeypatch.setattr(settings,'s3_endpoint',endpoint);remote.fail_delete=True
    cleanup_accounts();assert receipt(client,key).json()['media_cleanup']=='scheduled'
    remote.fail_delete=False;cleanup_accounts()
    assert set(remote.objects)=={'media/other-owner/keep'}
    assert receipt(client,key).json()['media_cleanup']=='verified'


def test_collision_cannot_disable_another_account(client):
    first=new_user(client);second=new_user(client);key=str(uuid.uuid4())
    assert request(client,first,key).status_code==202
    assert request(client,second,key).status_code==409
    assert client.get('/api/v1/me',headers=headers(second)).status_code==200


def test_deletion_serializes_against_late_admission(client,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from upload_fixtures import RIGHTS_FORM
    token=new_user(client);probing=Event();resume=Event()
    def probe(_):
        probing.set();assert resume.wait(10)
        return {'duration':2,'width':320,'height':240}
    monkeypatch.setattr('app.main.probe_video',probe)
    def upload():return client.post('/api/v1/jobs',headers=headers(token),files={'file':('source.mp4',b'private','video/mp4')},data=RIGHTS_FORM)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending=pool.submit(upload);assert probing.wait(10)
        from fastapi.testclient import TestClient
        from app.main import app
        try:
            with TestClient(app) as second_client:
                assert request(second_client,token).status_code==202
        finally:resume.set()
        assert pending.result(timeout=15).status_code==401


def test_password_deletion_rate_limit_is_persisted(client,monkeypatch):
    monkeypatch.setattr(settings,'auth_password_limit',1)
    token=new_user(client)
    assert request(client,token,password='wrong').status_code==400
    denied=request(client,token)
    assert denied.status_code==429 and denied.headers.get('retry-after')
    assert client.get('/api/v1/me',headers=headers(token)).status_code==200


def test_owner_symlink_is_refused(client,monkeypatch,tmp_path):
    import shutil,os
    jid,token=queued_job(client,monkeypatch)
    with SessionLocal() as db:uid=db.get(RenderJob,jid).user_id
    assert request(client,token).status_code==202;due(uid)
    root=settings.storage_dir/uid;shutil.rmtree(root)
    outside=tmp_path/'outside';outside.mkdir();(outside/'keep').write_bytes(b'keep')
    try:root.symlink_to(outside,target_is_directory=True)
    except OSError as error:
        if os.name=='nt' and getattr(error,'winerror',None)==1314:pytest.skip('Windows requires Developer Mode for symlinks')
        raise
    cleanup_accounts();assert (outside/'keep').exists()
    with SessionLocal() as db:assert db.get(AccountDeletion,uid).media_cleaned_at is None
    root.unlink()


def test_pending_upload_parts_are_removed_only_after_confirmed_cleanup(client,context):
    from test_upload_sessions import create,fill
    from app.models import UploadSession,UploadPart
    from app.storage import usage
    from app.uploads import part_directory
    owner,other,uid=context
    session=create(client,owner,total=24).json();sid=session['id']
    fill(client,owner,sid,b'abcdefghijklmnopqrstuvwx')
    token=owner['Authorization'].split(' ',1)[1];key=str(uuid.uuid4())
    assert request(client,token,key).status_code==202
    with SessionLocal() as db:
        row=db.get(UploadSession,sid)
        assert row.status=='aborted' and not row.parts_cleaned
        assert usage(db,uid)['known_reserved_bytes']>0
        assert db.scalar(select(UploadPart).where(UploadPart.session_id==sid))
    assert part_directory(uid,sid).exists()
    due(uid);cleanup_accounts()
    with SessionLocal() as db:
        assert db.get(UploadSession,sid).parts_cleaned
        assert not db.scalar(select(UploadPart).where(UploadPart.session_id==sid))
        assert usage(db,uid)['known_reserved_bytes']==0
    assert not part_directory(uid,sid).exists()
