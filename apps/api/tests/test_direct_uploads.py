import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from app import object_store as store
from app.config import get_settings
from app.db import SessionLocal
from app.models import DirectUploadGrant, UploadSession, UploadPart, RenderJob, utcnow
from app.storage import reservation, usage
from app.upload_cleanup import cleanup_uploads
from test_object_store import remote
from test_upload_sessions import context, create, put


@pytest.fixture
def direct(remote, monkeypatch):
    monkeypatch.setattr(get_settings(), 'direct_uploads_enabled', True)
    return remote


def intent(client, owner, sid, offset, data):
    return client.post(f'/api/v1/upload-sessions/{sid}/part-url', headers=owner,
        json={'offset':offset,'sha256':hashlib.sha256(data).hexdigest()})


def stage(remote, owner_id, sid, grant, data):
    remote.objects[store.upload_key(owner_id,sid,grant['grant_id'])]=(data,{'sha256':hashlib.sha256(data).hexdigest()})


def commit(client, owner, sid, grant):
    return client.post(f'/api/v1/upload-sessions/{sid}/part-commit/{grant["grant_id"]}',headers=owner)


def test_direct_transport_is_opt_in_and_does_not_change_submission_digest(client,context,monkeypatch):
    owner,_,_=context;key=uuid.uuid4().hex
    first=create(client,owner,key=key).json()
    monkeypatch.setattr(get_settings(),'direct_uploads_enabled',True)
    replay=create(client,owner,key=key,direct_upload=True).json()
    assert first['id']==replay['id'] and replay['transfer_backend']=='api'
    assert create(client,owner,direct_upload='true').status_code==422
    assert intent(client,owner,first['id'],0,b'abcdefgh').status_code==409


def test_direct_seal_survives_mutable_incoming_and_completes_as_one_job(client,context,direct):
    owner,other,uid=context;sid=create(client,owner,direct_upload=True).json()['id']
    source=b'abcdefghijklmnopqrstuvwx'
    assert put(client,owner,sid,0,source[:8]).status_code==409
    for offset in (0,8,16):
        denied=intent(client,other,sid,offset,source[offset:offset+8]);assert denied.status_code==404
        signed=intent(client,owner,sid,offset,source[offset:offset+8]);assert signed.status_code==200
        assert signed.headers['cache-control']=='private, no-store'
        grant=signed.json();assert 'content-length' in grant['url'] and 'x-amz-checksum-sha256' in grant['url']
        assert commit(client,other,sid,grant).status_code==404
        assert grant['headers']['Content-Length']=='8'
        stage(direct,uid,sid,grant,source[offset:offset+8])
        result=commit(client,owner,sid,grant);assert result.status_code==200
        assert result.json()['received_bytes']==offset+8
        assert commit(client,owner,sid,grant).json()['received_bytes']==offset+8
        # A leaked still-live PUT capability can never target the sealed key.
        direct.objects[store.upload_key(uid,sid,grant['grant_id'])]=(b'bad-data',{'sha256':'0'*64})
    done=client.post(f'/api/v1/upload-sessions/{sid}/complete',headers=owner)
    assert done.status_code==200
    assert client.post(f'/api/v1/upload-sessions/{sid}/complete',headers=owner).json()['id']==done.json()['id']
    with SessionLocal() as db:
        row=db.get(RenderJob,done.json()['id']);assert row.media_backend=='s3'
        assert direct.objects[store.source_key(uid,row.id,'.mp4')][0]==source
        assert row.storage_reserved_bytes==reservation(3*len(source),get_settings().max_render_bytes)
        assert db.scalar(select(func.count()).select_from(RenderJob).where(RenderJob.user_id==uid))==1


@pytest.mark.parametrize('bytes_', [b'too-short', b'1234567', b'wrong123'])
def test_bad_direct_bytes_never_advance_offset(client,context,direct,bytes_):
    owner,_,uid=context;sid=create(client,owner,direct_upload=True).json()['id']
    grant=intent(client,owner,sid,0,b'abcdefgh').json()
    # Even if the provider lets an attacker lie about metadata, full SHA is checked.
    direct.objects[store.upload_key(uid,sid,grant['grant_id'])]=(bytes_,{'sha256':hashlib.sha256(b'abcdefgh').hexdigest()})
    assert commit(client,owner,sid,grant).status_code==409
    assert client.get(f'/api/v1/upload-sessions/{sid}',headers=owner).json()['received_bytes']==0
    with SessionLocal() as db:assert db.get(UploadPart,(sid,0)) is None


def test_renewal_reuses_one_bounded_key_and_refuses_changed_bytes(client,context,direct):
    owner,_,_=context;sid=create(client,owner,direct_upload=True).json()['id']
    first=intent(client,owner,sid,0,b'abcdefgh').json()
    with SessionLocal.begin() as db:db.get(DirectUploadGrant,first['grant_id']).expires_at=utcnow()-timedelta(seconds=1)
    second=intent(client,owner,sid,0,b'abcdefgh').json();assert first['grant_id']==second['grant_id']
    assert intent(client,owner,sid,0,b'changed!').status_code==409
    assert intent(client,owner,sid,8,b'abcdefgh').status_code==409
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(DirectUploadGrant).where(DirectUploadGrant.session_id==sid))==1


def test_concurrent_direct_commits_preserve_one_offset(client,context,direct):
    owner,_,uid=context;sid=create(client,owner,direct_upload=True).json()['id']
    grant=intent(client,owner,sid,0,b'abcdefgh').json();stage(direct,uid,sid,grant,b'abcdefgh')
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:commit(client,owner,sid,grant),range(2)))
    assert all(result.status_code==200 and result.json()['received_bytes']==8 for result in results)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(UploadPart).where(UploadPart.session_id==sid))==1
    assert intent(client,owner,sid,0,b'abcdefgh').json()['committed'] is True


def test_abort_during_sealing_cannot_commit_and_cleanup_waits_for_capability(client,context,direct):
    owner,_,uid=context;sid=create(client,owner,direct_upload=True).json()['id']
    grant=intent(client,owner,sid,0,b'abcdefgh').json();stage(direct,uid,sid,grant,b'abcdefgh')
    original=direct.put_object
    def racing_put(**args):
        original(**args)
        if '/sealed/' in args['Key']:
            assert client.post(f'/api/v1/upload-sessions/{sid}/abort',headers=owner).status_code==200
    direct.put_object=racing_put
    assert commit(client,owner,sid,grant).status_code==409
    cleanup_uploads()
    with SessionLocal() as db:
        assert db.get(UploadSession,sid).received_bytes==0 and not db.get(UploadSession,sid).parts_cleaned
        assert usage(db,uid)['known_reserved_bytes']>0
    assert intent(client,owner,sid,0,b'abcdefgh').status_code==409
    with SessionLocal.begin() as db:db.get(DirectUploadGrant,grant['grant_id']).expires_at=utcnow()-timedelta(seconds=1)
    cleanup_uploads()
    with SessionLocal() as db:assert db.get(UploadSession,sid).parts_cleaned and usage(db,uid)['known_reserved_bytes']==0
    assert not any(key.startswith(store.upload_prefix(uid,sid)) for key in direct.objects)
    # Resweep late/in-flight writes even after a previous cleanup was marked done.
    stage(direct,uid,sid,grant,b'abcdefgh');cleanup_uploads()
    assert not any(key.startswith(store.upload_prefix(uid,sid)) for key in direct.objects)


def test_direct_namespace_change_and_missing_consent_fail_closed(client,context,direct,monkeypatch):
    owner,_,_=context;sid=create(client,owner,direct_upload=True).json()['id']
    endpoint=get_settings().s3_endpoint
    monkeypatch.setattr(get_settings(),'s3_endpoint','http://localhost:8333')
    assert intent(client,owner,sid,0,b'abcdefgh').status_code==503
    monkeypatch.setattr(get_settings(),'s3_endpoint',endpoint)
    with SessionLocal.begin() as db:db.get(UploadSession,sid).rights_confirmed_at=None
    assert intent(client,owner,sid,0,b'abcdefgh').status_code==409
