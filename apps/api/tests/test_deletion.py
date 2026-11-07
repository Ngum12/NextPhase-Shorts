from upload_fixtures import RIGHTS_FORM
from datetime import timedelta
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select
from app.db import SessionLocal
from app.deletion import cleanup_deleted, remove_private_tree
from app.models import RenderAttempt, RenderJob, UploadSession, utcnow
from app.worker import claim_job, mark_done, process, settings
from test_worker import queued_job
from test_api import new_user
from test_upload_sessions import context


def auth(token):return {'Authorization':'Bearer '+token}
def remove(client,job_id,token):return client.delete('/api/v1/jobs/'+job_id,headers=auth(token))


@pytest.mark.parametrize('status',['queued','processing','succeeded','failed','cancelled'])
def test_delete_is_private_repeatable_hidden_and_fenced(client,monkeypatch,status):
    job_id,token=queued_job(client,monkeypatch)
    other=new_user(client)
    assert client.delete('/api/v1/jobs/'+job_id).status_code==401
    assert remove(client,job_id,other).status_code==404
    old=None
    if status=='processing':old=claim_job()
    with SessionLocal.begin() as db:
        job=db.get(RenderJob,job_id);owner_id=job.user_id
        if status!='processing':job.status=status
        directory=settings.storage_dir/owner_id/job_id
        (directory/'output.mp4').write_bytes(b'rendered')
        job.output_path=str(directory/'output.mp4')
    assert remove(client,job_id,token).status_code==202
    assert remove(client,job_id,token).json()=={'status':'deleted','media_cleanup':'scheduled'}
    assert remove(client,job_id,other).status_code==404
    assert job_id not in {row['id'] for row in client.get('/api/v1/jobs',headers=auth(token)).json()}
    for suffix in ('','/download'):
        assert client.get('/api/v1/jobs/'+job_id+suffix,headers=auth(token)).status_code==404
    assert client.post('/api/v1/jobs/'+job_id+'/cancel',headers=auth(token)).status_code==404
    with SessionLocal() as db:
        job=db.get(RenderJob,job_id)
        assert job.status=='deleted' and job.deleted_at and job.claim_token is None
        assert job.source_path=='' and job.output_path is None and job.title=='Deleted project'
    if old:
        assert not mark_done(job_id,old['claim_token'],error_code='LATE')
        process(old)
        assert directory.exists() # Still inside its original bounded lease window.
        with SessionLocal.begin() as db:db.get(RenderJob,job_id).cleanup_after=utcnow()-timedelta(seconds=1)
    cleanup_deleted()
    assert not directory.exists()
    # Recreated stale directories are swept again, not trusted as permanently gone.
    directory.mkdir(parents=True);(directory/'late.mp4').write_bytes(b'late')
    cleanup_deleted();assert not directory.exists()


def test_deleted_idempotency_key_cannot_recreate_job(client,monkeypatch):
    monkeypatch.setattr('app.main.probe_video',lambda _: {'duration':2,'width':320,'height':240})
    token=new_user(client);key=uuid.uuid4().hex
    def upload():return client.post('/api/v1/jobs',headers={**auth(token),'Idempotency-Key':key},
        files={'file':('source.mp4',b'original','video/mp4')}, data=RIGHTS_FORM)
    job_id=upload().json()['id']
    remove(client,job_id,token)
    assert upload().status_code==410
    assert client.get('/api/v1/jobs',headers=auth(token)).json()==[]


def test_failed_cleanup_retries_without_exposing_paths(client,monkeypatch,caplog):
    job_id,token=queued_job(client,monkeypatch);remove(client,job_id,token)
    import app.deletion as deletion
    original=deletion.remove_private_tree
    def fail(*args,**kwargs):raise PermissionError('sensitive-private-path')
    monkeypatch.setattr(deletion,'remove_private_tree',fail)
    cleanup_deleted()
    with SessionLocal() as db:
        row=db.get(RenderJob,job_id);assert row.media_deleted_at is None and row.cleanup_attempted_at
    assert 'sensitive-private-path' not in caplog.text
    monkeypatch.setattr(deletion,'remove_private_tree',original);cleanup_deleted()
    with SessionLocal() as db:assert db.get(RenderJob,job_id).media_deleted_at


def test_only_derived_private_paths_are_removed_and_symlinks_not_followed(client,monkeypatch,tmp_path):
    job_id,token=queued_job(client,monkeypatch)
    outside=tmp_path/'outside';outside.mkdir();valuable=outside/'keep';valuable.write_bytes(b'keep')
    with SessionLocal.begin() as db:
        row=db.get(RenderJob,job_id);owner_id=row.user_id;row.source_path=str(valuable);row.output_path=str(valuable)
    remove(client,job_id,token);cleanup_deleted();assert valuable.exists()
    with pytest.raises(ValueError):remove_private_tree(owner_id,'../outside')


def test_cleanup_refuses_parent_symlinks_and_unlinks_leaf_symlinks(client,monkeypatch,tmp_path):
    job_id,token=queued_job(client,monkeypatch)
    outside=tmp_path/'outside';outside.mkdir();valuable=outside/'keep';valuable.write_bytes(b'keep')
    with SessionLocal() as db:owner_id=db.get(RenderJob,job_id).user_id
    remove(client,job_id,token);cleanup_deleted()
    owner=settings.storage_dir/owner_id
    import shutil,os
    shutil.rmtree(owner)
    try:owner.symlink_to(outside,target_is_directory=True)
    except OSError as error:
        if os.name=='nt' and getattr(error,'winerror',None)==1314:
            pytest.skip('Windows symlink creation requires Developer Mode or administrator privileges')
        raise
    cleanup_deleted();assert valuable.exists()
    owner.unlink();owner.mkdir()
    (owner/job_id).symlink_to(outside,target_is_directory=True)
    cleanup_deleted();assert valuable.exists() and not (owner/job_id).exists()


def test_concurrent_delete_and_completion_cannot_resurrect(client,monkeypatch):
    job_id,token=queued_job(client,monkeypatch);claimed=claim_job()
    with ThreadPoolExecutor(max_workers=2) as pool:
        deletion=pool.submit(remove,client,job_id,token)
        completion=pool.submit(mark_done,job_id,claimed['claim_token'],error_code='TEST')
        assert deletion.result().status_code==202;completion.result()
    with SessionLocal() as db:assert db.get(RenderJob,job_id).status=='deleted'
    assert client.get('/api/v1/jobs/'+job_id+'/download',headers=auth(token)).status_code==404


def test_completed_upload_sessions_and_parts_follow_project_deletion(client,context):
    from test_upload_sessions import create,fill
    from app.uploads import part_directory
    owner,other,owner_id=context
    session=create(client,owner,total=24).json();sid=session['id']
    fill(client,owner,sid,b'abcdefghijklmnopqrstuvwx')
    job_id=client.post(f'/api/v1/upload-sessions/{sid}/complete',headers=owner).json()['id']
    directory=part_directory(owner_id,sid);directory.mkdir(parents=True,exist_ok=True)
    (directory/'leftover.part').write_bytes(b'private')
    assert client.delete('/api/v1/jobs/'+job_id,headers=owner).status_code==202
    for suffix in ('','/complete'):
        response=(client.get if not suffix else client.post)(f'/api/v1/upload-sessions/{sid}'+suffix,headers=owner)
        assert response.status_code==410
    key=None
    with SessionLocal() as db:key=db.get(UploadSession,sid).client_key
    assert create(client,owner,total=24,key=key).status_code==410
    cleanup_deleted();assert not directory.exists()
    with SessionLocal() as db:
        row=db.get(UploadSession,sid)
        assert row.parts_cleaned and row.file_name=='deleted.mp4' and row.source_sha256 is None


def test_deletion_stops_a_real_running_ffmpeg_attempt(client,monkeypatch):
    import subprocess
    import app.worker as worker
    job_id,token=queued_job(client,monkeypatch)
    with SessionLocal.begin() as db:
        row=db.get(RenderJob,job_id);row.desired_seconds=60;row.source_duration_seconds=60
    job=claim_job()
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','color=c=navy:s=160x90:r=30',
        '-t','60','-c:v','libx264','-pix_fmt','yuv420p',job['source']],check=True,timeout=30)
    original_check=worker.owns_claim;checks=0
    def check(current):
        nonlocal checks
        checks+=1
        if checks==3:assert remove(client,job_id,token).status_code==202
        return original_check(current)
    original_popen=subprocess.Popen;children=[]
    def record(*args,**kwargs):
        child=original_popen(*args,**kwargs)
        if 'ffmpeg' in args[0]:children.append(child)
        return child
    monkeypatch.setattr(worker,'owns_claim',check)
    monkeypatch.setattr('app.media.subprocess.Popen',record)
    process(job)
    assert checks>=3 and len(children)==1 and children[0].poll() is not None
    assert children[0].returncode!=0
    with SessionLocal() as db:
        assert db.get(RenderJob,job_id).status=='deleted'
        assert db.get(RenderAttempt,job['claim_token']).status=='cancelled'
    directory=settings.storage_dir/job['user_id']/job_id
    assert not list(directory.rglob('output*.mp4'))


def test_completion_race_after_attempt_update_uses_consistent_lock_order(client,monkeypatch):
    from sqlalchemy import event
    from app.db import engine
    from threading import Event
    job_id,token=queued_job(client,monkeypatch);claimed=claim_job()
    attempt_updated=Event();completion_started=Event();completion_finished=Event()
    def after_update(connection,cursor,statement,parameters,context,executemany):
        values=parameters.values() if isinstance(parameters,dict) else parameters
        if statement.startswith('UPDATE render_attempts') and 'cancelled' in values and not attempt_updated.is_set():
            attempt_updated.set()
            assert completion_started.wait(5)
            assert not completion_finished.wait(.1)
    def complete():
        assert attempt_updated.wait(5)
        completion_started.set()
        try:return mark_done(job_id,claimed['claim_token'],error_code='LATE')
        finally:completion_finished.set()
    event.listen(engine,'after_cursor_execute',after_update)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            late=pool.submit(complete)
            deletion=pool.submit(remove,client,job_id,token)
            assert deletion.result(timeout=15).status_code==202
            assert not late.result(timeout=15)
    finally:event.remove(engine,'after_cursor_execute',after_update)


def test_cleanup_prioritizes_new_pending_removal_over_old_successful_rescans(client,monkeypatch):
    old,token=queued_job(client,monkeypatch);remove(client,old,token);cleanup_deleted()
    with SessionLocal.begin() as db:
        row=db.get(RenderJob,old);row.cleanup_attempted_at=utcnow()-timedelta(days=10)
    new,new_token=queued_job(client,monkeypatch);remove(client,new,new_token)
    cleanup_deleted(limit=1)
    with SessionLocal() as db:assert db.get(RenderJob,new).media_deleted_at is not None
