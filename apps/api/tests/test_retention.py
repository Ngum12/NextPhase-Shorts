from datetime import timedelta
import hashlib
import os
from pathlib import Path
import uuid
import pytest
from sqlalchemy import select, update
from botocore.exceptions import ClientError
from app.config import get_settings
from app.db import SessionLocal
from app.models import User,RenderJob,RenderAttempt,UploadSession,utcnow
from app import retention
from app import object_store as store
from app.upload_cleanup import cleanup_uploads
from app.storage import usage
from test_object_store import remote


@pytest.fixture
def owner(monkeypatch,tmp_path):
    root=tmp_path/'media';root.mkdir();monkeypatch.setattr(get_settings(),'storage_dir',root)
    uid=str(uuid.uuid4())
    with SessionLocal.begin() as db:db.add(User(id=uid,email=uid+'@example.com',password_hash='synthetic'))
    yield uid
    with SessionLocal.begin() as db:
        db.execute(update(RenderJob).where(RenderJob.user_id==uid,RenderJob.status.in_(('queued','processing'))).values(status='cancelled'))
        db.execute(update(UploadSession).where(UploadSession.user_id==uid).values(status='aborted',parts_cleaned=True))


def old_now():return utcnow()+timedelta(days=2)


def tree(owner,entity=None):
    entity=entity or str(uuid.uuid4());path=get_settings().storage_dir/owner/entity
    path.mkdir(parents=True);(path/'input.mp4').write_bytes(b'synthetic')
    return entity,path


def job(owner,jid,**values):
    with SessionLocal.begin() as db:
        db.add(RenderJob(id=jid,user_id=owner,title='Protected',style='vlog',desired_seconds=15,
            source_duration_seconds=2,source_path=values.pop('source_path','input.mp4'),status=values.pop('status','succeeded'),**values))


def test_preview_only_then_exact_digest_offline_orphan_removal(owner):
    jid,path=tree(owner);now=old_now();plan=retention.preview(now=now)
    assert plan['candidate_groups']==1 and path.exists()
    with pytest.raises(retention.RetentionError):retention.apply(plan['digest'],now=now)
    with pytest.raises(retention.RetentionError):retention.apply('forged',offline=True,now=now)
    result=retention.apply(plan['digest'],offline=True,now=now)
    assert result['removed_groups']==1 and result['failed_groups']==0 and not path.exists()
    assert retention.preview(now=now)['candidate_groups']==0


@pytest.mark.parametrize('status',['queued','processing','succeeded','failed','cancelled','deleted'])
def test_known_project_in_every_state_is_retained(owner,status):
    jid,path=tree(owner);job(owner,jid,status=status)
    assert retention.preview(now=old_now())['candidate_groups']==0 and (path/'input.mp4').exists()


def test_new_or_changed_or_committed_candidate_refuses_apply(owner):
    jid,path=tree(owner)
    assert retention.preview()['candidate_groups']==0
    now=old_now();plan=retention.preview(now=now)
    (path/'input.mp4').write_bytes(b'changed')
    with pytest.raises(retention.RetentionError):retention.apply(plan['digest'],offline=True,now=now)
    plan=retention.preview(now=now);job(owner,jid)
    with pytest.raises(retention.RetentionError):retention.apply(plan['digest'],offline=True,now=now)
    assert path.exists()


def test_unknown_files_links_and_unknown_owners_are_never_candidates(owner,tmp_path):
    _,path=tree(owner);(path/'personal.txt').write_text('keep')
    _,foreign=tree(str(uuid.uuid4()))
    assert retention.preview(now=old_now())['candidate_groups']==0
    (path/'personal.txt').unlink()
    original=tmp_path/'important';original.write_bytes(b'keep')
    (path/'input.mp4').unlink()
    try:os.link(original,path/'input.mp4')
    except OSError:pytest.skip('Hardlinks unavailable')
    assert retention.preview(now=old_now())['candidate_groups']==0 and original.read_bytes()==b'keep'


def test_symlink_parent_is_not_followed(owner,tmp_path):
    target=tmp_path/'outside';target.mkdir();jid=str(uuid.uuid4());(target/jid).mkdir()
    (target/jid/'input.mp4').write_bytes(b'keep')
    try:(get_settings().storage_dir/owner).symlink_to(target,target_is_directory=True)
    except OSError:pytest.skip('Symlink privileges unavailable')
    assert retention.preview(now=old_now())['candidate_groups']==0
    assert (target/jid/'input.mp4').read_bytes()==b'keep'


def test_scan_limit_and_grace_floor_fail_closed(owner):
    _,path=tree(owner);plan=retention.preview(scan_limit=1,now=old_now())
    assert plan['truncated']
    with pytest.raises(retention.RetentionError):retention.apply(plan['digest'],offline=True,scan_limit=1,now=old_now())
    with pytest.raises(retention.RetentionError):retention.preview(grace_hours=0)
    assert path.exists()


def test_stale_attempt_cleanup_preserves_winner_and_source(owner):
    jid,root=tree(owner);loser,winner=str(uuid.uuid4()),str(uuid.uuid4())
    for token in (loser,winner):(root/token).mkdir();(root/token/'output.mp4').write_bytes(token.encode())
    job(owner,jid,claim_token=winner,output_path=str(root/winner/'output.mp4'))
    with SessionLocal.begin() as db:
        db.add(RenderAttempt(id=loser,job_id=jid,number=1,status='lease_lost',started_at=utcnow()))
        db.add(RenderAttempt(id=winner,job_id=jid,number=2,status='succeeded',started_at=utcnow()))
    now=old_now();plan=retention.preview(now=now)
    assert plan['candidate_groups']==1 and plan['candidates'][0]['token']==loser
    result=retention.apply(plan['digest'],offline=True,now=now)
    assert result['removed_groups']==1 and not (root/loser).exists()
    assert (root/winner/'output.mp4').exists() and (root/'input.mp4').exists()


def test_orphan_upload_tree_is_removed_but_known_session_is_preserved(owner):
    sid=str(uuid.uuid4());root=get_settings().storage_dir/owner/'.uploads'/sid;root.mkdir(parents=True)
    (root/('0-'+'a'*64+'.part')).write_bytes(b'chunk')
    now=old_now();plan=retention.preview(now=now);assert plan['candidate_groups']==1
    with SessionLocal.begin() as db:db.add(UploadSession(id=sid,user_id=owner,client_key='retention-key',descriptor_hash='a'*64,
        file_name='input.mp4',extension='.mp4',title='Keep',style='vlog',desired_seconds=15,total_bytes=8,received_bytes=0,
        chunk_bytes=8,expires_at=utcnow()+timedelta(days=3)))
    with pytest.raises(retention.RetentionError):retention.apply(plan['digest'],offline=True,now=now)
    assert root.exists()


@pytest.fixture
def objects(remote,monkeypatch):
    stamp=utcnow()
    original_head=remote.head_object
    def head(**args):
        result=original_head(**args);data=remote.objects[args['Key']][0]
        return {**result,'ETag':'"'+hashlib.sha256(data).hexdigest()+'"','LastModified':stamp}
    def listing(**args):
        keys=sorted(key for key in remote.objects if key.startswith(args['Prefix']))
        start=int(args.get('ContinuationToken',0));end=start+args['MaxKeys']
        return {'Contents':[{'Key':key,'ETag':head(Key=key)['ETag'],'Size':len(remote.objects[key][0]),'LastModified':stamp} for key in keys[start:end]],
            'IsTruncated':end<len(keys),**({'NextContinuationToken':str(end)} if end<len(keys) else {})}
    def delete(**args):
        if remote.fail_delete:raise ClientError({'Error':{'Code':'AccessDenied'}},'DeleteObject')
        remote.objects.pop(args['Key'],None)
    monkeypatch.setattr(remote,'head_bucket',lambda **_: {},raising=False)
    monkeypatch.setattr(remote,'head_object',head);monkeypatch.setattr(remote,'list_objects_v2',listing)
    monkeypatch.setattr(remote,'delete_object',delete,raising=False)
    return remote


def test_remote_preview_removal_partial_failure_and_namespace_digest(owner,objects,monkeypatch):
    jid=str(uuid.uuid4());key=store.source_key(owner,jid,'.mp4');objects.objects[key]=(b'orphan',{})
    now=old_now();plan=retention.preview('s3',now=now);assert plan['candidate_groups']==1
    endpoint=get_settings().s3_endpoint
    monkeypatch.setattr(get_settings(),'s3_endpoint','http://localhost:8333')
    with pytest.raises(retention.RetentionError):retention.apply(plan['digest'],backend='s3',offline=True,now=now)
    monkeypatch.setattr(get_settings(),'s3_endpoint',endpoint)
    objects.fail_delete=True;result=retention.apply(plan['digest'],backend='s3',offline=True,now=now)
    assert result['failed_groups']==1 and key in objects.objects
    objects.fail_delete=False;result=retention.apply(plan['digest'],backend='s3',offline=True,now=now)
    assert result['removed_groups']==1 and key not in objects.objects


def test_remote_valid_projects_and_uploads_protected_and_versions_refused(owner,objects):
    jid=str(uuid.uuid4());job(owner,jid,media_backend='s3',object_store_id=store.namespace_id())
    keep=store.source_key(owner,jid,'.mp4');objects.objects[keep]=(b'keep',{})
    sid=str(uuid.uuid4());grant=str(uuid.uuid4());key=store.upload_key(owner,sid,grant);objects.objects[key]=(b'orphan',{})
    plan=retention.preview('s3',now=old_now());assert plan['candidate_groups']==1
    retention.apply(plan['digest'],backend='s3',offline=True,now=old_now());assert keep in objects.objects and key not in objects.objects
    objects.versioned=True
    with pytest.raises(store.ObjectStoreError):retention.preview('s3',now=old_now())


def test_expiration_is_bounded_and_releases_only_cleaned_reservations(owner):
    with SessionLocal.begin() as db:
        for index in range(4):
            db.add(UploadSession(id=str(uuid.uuid4()),user_id=owner,client_key='expire-'+str(index),descriptor_hash='a'*64,
                file_name='input.mp4',extension='.mp4',title='Expired',style='vlog',desired_seconds=15,total_bytes=8,received_bytes=0,
                chunk_bytes=8,expires_at=utcnow()-timedelta(hours=2),storage_reserved_bytes=100,max_render_bytes=1048576))
    with pytest.raises(ValueError):cleanup_uploads(0)
    cleanup_uploads(limit=2)
    with SessionLocal() as db:
        rows=list(db.scalars(select(UploadSession).where(UploadSession.user_id==owner)))
        assert sum(row.status=='uploading' for row in rows)==2
        assert usage(db,owner)['known_reserved_bytes']>=200


def test_attempt_referenced_by_another_project_is_preserved(owner):
    jid,root=tree(owner);loser,winner=str(uuid.uuid4()),str(uuid.uuid4())
    (root/loser).mkdir();(root/loser/'output.mp4').write_bytes(b'referenced')
    job(owner,jid,claim_token=winner)
    job(owner,str(uuid.uuid4()),source_path=str(root/loser/'output.mp4'))
    with SessionLocal.begin() as db:db.add(RenderAttempt(id=loser,job_id=jid,number=1,status='lease_lost',started_at=utcnow()))
    assert retention.preview(now=old_now())['candidate_groups']==0


def test_unregistered_tree_referenced_by_a_valid_project_is_preserved(owner):
    entity,path=tree(owner)
    job(owner,str(uuid.uuid4()),source_path=str(path/'input.mp4'))
    assert retention.preview(now=old_now())['candidate_groups']==0
    assert (path/'input.mp4').exists()


def test_nonprogressing_remote_listing_is_refused(owner,objects,monkeypatch):
    monkeypatch.setattr(objects,'list_objects_v2',lambda **_: {'Contents':[], 'IsTruncated':True,'NextContinuationToken':'same'})
    with pytest.raises(retention.RetentionError):retention.preview('s3',now=old_now())
