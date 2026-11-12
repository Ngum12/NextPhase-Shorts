"""Analysis admission and publication fences; no real recognition claimed here."""
from datetime import timedelta
import uuid
import pytest
from sqlalchemy import select,update
from app.config import get_settings
from app.db import SessionLocal
from app.models import RenderJob,RenderAttempt,UploadSession,ProjectAnalysis,utcnow
from app.automatic_analysis import publish,reconcile_requested
from test_project_analysis import prepared,imported
from test_migrations import migration_engine

@pytest.fixture
def automatic(prepared,monkeypatch):
    monkeypatch.setattr(get_settings(),'english_analysis_enabled',True)
    monkeypatch.setattr(get_settings(),'english_analysis_model_sha256','b'*64)
    return {**prepared,'auto':'/api/v1/english-analysis/jobs/'+prepared['jid']}

def start(client,item,key=None,**extra):
    return client.post(item['auto'],headers=item['owner'],json=dict(idempotency_key=key or str(uuid.uuid4()),acknowledged_server_analysis=True,**extra))

def claimed(identity):
    with SessionLocal.begin() as db:
        row=db.get(RenderJob,identity);row.status='processing';row.claim_token=str(uuid.uuid4())
        row.lease_expires_at=row.claim_deadline_at=utcnow()+timedelta(minutes=10)
        db.add(RenderAttempt(id=row.claim_token,job_id=row.id,number=1,status='running',started_at=utcnow(),deadline_at=row.claim_deadline_at))
        return dict(id=row.id,user_id=row.user_id,claim_token=row.claim_token,preview_parent_id=row.preview_parent_id)

def test_private_capabilities_optin_replay_and_hidden_nonvideo_task(client,automatic):
    item=automatic
    caps=client.get('/api/v1/english-analysis/capabilities',headers=item['owner'])
    assert caps.json()['available'] and caps.headers['cache-control']=='private, no-store'
    key=str(uuid.uuid4());first=start(client,item,key)
    assert first.status_code==202,first.text
    child=first.json()['task'];assert child['operation']=='analysis' and child['status']=='queued'
    assert start(client,item,key).json()['task']['id']==child['id']
    assert start(client,item).json()['task']['id']==child['id']
    assert child['id'] not in [j['id'] for j in client.get('/api/v1/jobs',headers=item['owner']).json()]
    assert client.get(item['auto'],headers=item['other']).status_code==404
    assert client.get(item['auto']).status_code==401
    assert client.post(item['auto'],headers=item['owner'],json=dict(idempotency_key=str(uuid.uuid4()),acknowledged_server_analysis=False)).status_code==422
    with SessionLocal() as db:
        task=db.get(RenderJob,child['id'])
        assert not task.source_path and task.storage_reserved_bytes>80*1024**2
    assert client.get('/api/v1/jobs/'+child['id']+'/download',headers=item['owner']).status_code==409

def test_publish_is_review_required_idempotent_and_preserves_existing_annotations(client,automatic):
    item=automatic;child=start(client,item).json()['task']['id'];job=claimed(child)
    assert publish(job,item['transcript'],1)
    state=client.get(item['auto'],headers=item['owner']).json()
    assert state['ready'] and state['task']['status']=='succeeded'
    assert not publish(job,item['transcript'],1)
    review=client.get(item['url'],headers=item['owner']).json()
    assert review['review'] is None and review['proposal']['human_review_required'] and not review['render_enabled']
    assert start(client,item).json()['task']['id']==child

def test_cancel_revokes_claim_and_pending_intent_retry_uses_new_terminal_key(client,automatic):
    item=automatic;child=start(client,item).json()['task']['id'];job=claimed(child)
    with SessionLocal.begin() as db:
        upload=db.scalar(select(UploadSession).where(UploadSession.job_id==item['jid']));upload.english_analysis=True
    result=client.post(item['auto']+'/cancel',headers=item['owner'])
    assert result.status_code==200 and result.json()['task']['status']=='cancelled' and not result.json()['requested']
    assert not publish(job,item['transcript'],1)
    with SessionLocal() as db:
        assert db.get(RenderJob,child).claim_deadline_at is not None
        assert db.get(ProjectAnalysis,item['jid']) is None
    second=start(client,item,child,retry_failed=True).json()['task']['id']
    assert second!=child and start(client,item,child,retry_failed=True).json()['task']['id']==second

def test_source_delete_or_lease_expiry_blocks_publication(client,automatic):
    item=automatic;child=start(client,item).json()['task']['id'];job=claimed(child)
    with SessionLocal.begin() as db:db.get(RenderJob,child).lease_expires_at=utcnow()-timedelta(seconds=1)
    assert not publish(job,item['transcript'],1)
    assert client.delete('/api/v1/jobs/'+item['jid'],headers=item['owner']).status_code==202
    assert not publish(job,item['transcript'],1)
    with SessionLocal() as db:assert db.get(RenderJob,child).status=='deleted'

def test_bounded_pending_admission_and_cancelled_work_not_requeued(client,automatic):
    item=automatic
    with SessionLocal.begin() as db:db.scalar(select(UploadSession).where(UploadSession.job_id==item['jid'])).english_analysis=True
    assert reconcile_requested()==1
    child=client.get(item['auto'],headers=item['owner']).json()['task']['id']
    assert reconcile_requested()==0
    assert client.post(item['auto']+'/cancel',headers=item['owner']).status_code==200
    assert reconcile_requested()==0
    assert client.get(item['auto'],headers=item['owner']).json()['task']['id']==child

def test_long_sources_and_disabled_feature_preserve_original(client,automatic,monkeypatch):
    with SessionLocal.begin() as db:db.get(RenderJob,automatic['jid']).source_duration_seconds=181
    assert start(client,automatic).status_code==422
    assert not client.get(automatic['auto'],headers=automatic['owner']).json()['eligible']
    monkeypatch.setattr(get_settings(),'english_analysis_enabled',False)
    assert start(client,automatic).status_code==404
    assert client.get('/api/v1/jobs/'+automatic['jid'],headers=automatic['owner']).status_code==200

def test_upload_consent_is_durable_and_admission_recovers_after_capacity(client,automatic,monkeypatch):
    from test_upload_sessions import create,fill
    item=automatic;key=uuid.uuid4().hex
    session=create(client,item['owner'],total=8,key=key,english_analysis=True)
    assert session.status_code==201,session.text
    assert create(client,item['owner'],total=8,key=key,english_analysis=False).status_code==409
    sid=session.json()['id'];fill(client,item['owner'],sid,b'abcdefgh')
    # Force only the additional analysis admission to be full.
    from fastapi import HTTPException
    original=__import__('app.automatic_analysis',fromlist=['enqueue']).enqueue
    def no_capacity(*a,**kw):raise HTTPException(429,'Full fixture queue')
    monkeypatch.setattr('app.automatic_analysis.enqueue',no_capacity)
    result=client.post(f'/api/v1/upload-sessions/{sid}/complete',headers=item['owner'])
    assert result.status_code==200,result.text
    with SessionLocal.begin() as db:
        row=db.get(UploadSession,sid);assert row.english_analysis and row.status=='completed'
        parent=row.job_id;db.execute(update(RenderJob).where(RenderJob.user_id==item['uid']).values(status='cancelled'))
    monkeypatch.setattr('app.automatic_analysis.enqueue',original)
    assert reconcile_requested()==1
    state=client.get('/api/v1/english-analysis/jobs/'+parent,headers=item['owner']).json()
    assert state['task']['status']=='queued' and state['requested']


@pytest.mark.parametrize('visual_available',[True,False])
def test_worker_pipeline_copies_hashes_decodes_and_cleans_attempt(client,monkeypatch,tmp_path,visual_available):
    # Real accepted MP4 + real FFmpeg + executable protocol fixture. No actual ASR.
    from test_excerpt_jobs import actual as actual_fixture
    from app.worker import claim_job,process
    if not visual_available:
        from app.scene_analysis import SceneUnavailable
        def unavailable(*args,**kwargs):raise SceneUnavailable()
        monkeypatch.setattr('app.scene_analysis.analyze',unavailable)
    from app.contained_asr import transcribe
    from app.local_transcription import file_digest
    import sys,json
    item=actual_fixture.__wrapped__(client,monkeypatch,tmp_path)
    with SessionLocal.begin() as db:db.delete(db.get(ProjectAnalysis,item['jid']))
    model=tmp_path/'model';model.write_bytes(b'synthetic fixture only')
    engine=tmp_path/'engine'
    data={'params':{'translate':False},'result':{'language':'en'},'model':{'multilingual':True,'vocab':51865},
        'transcription':[{'text':' Hello.', 'tokens':[
            {'text':' Hello','id':2425,'offsets':{'from':0,'to':0},'p':.9},
            {'text':'.','id':13,'offsets':{'from':0,'to':0},'p':.95}]}]}
    engine.write_text(f'#!{sys.executable}\nimport sys\nfrom pathlib import Path\n'
        f'Path(sys.argv[sys.argv.index("-of")+1]+".json").write_text({json.dumps(json.dumps(data))})\n');engine.chmod(0o700)
    monkeypatch.setattr(get_settings(),'english_analysis_enabled',True)
    monkeypatch.setattr(get_settings(),'english_analysis_model_sha256',file_digest(model))
    monkeypatch.setattr('app.analysis_work.MODEL',model)
    def native(*a,**kw):return transcribe(*a,**kw,engine=engine,engine_digest=file_digest(engine))
    monkeypatch.setattr('app.analysis_work.transcribe',native)
    item['auto']='/api/v1/english-analysis/jobs/'+item['jid']
    child=start(client,item).json()['task']['id'];job=claim_job();assert job['id']==child
    process(job)
    result=client.get(item['auto'],headers=item['owner']).json()
    assert result['ready'] and result['task']['status']=='succeeded',result
    document=client.get(item['url'],headers=item['owner']).json()
    assert document['transcript']['timestamp_quality']=='model_token_estimate_adjusted'
    assert document['audio_timing']['source_sha256']==item['transcript'].source_sha256
    assert document['audio_timing']['method']=='pcm_window_energy'
    assert document['scene_analysis']['status']==('available' if visual_available else 'unavailable')
    assert document['scene_analysis']['source_sha256']==item['transcript'].source_sha256
    assert document['transcript']['words'][0]['text']=='Hello.'
    assert 'adjusted_word_timestamps' in document['proposal']['warnings']
    with SessionLocal() as db:
        row=db.get(RenderJob,child);assert row.output_path is None
        from pathlib import Path
        directory=get_settings().storage_dir/item['uid']/child/job['claim_token']
        assert not any((directory/name).exists() for name in ('input.media','audio.wav','transcript.json'))
        assert file_digest(Path(db.get(RenderJob,item['jid']).source_path))==item['transcript'].source_sha256


def test_upgrade_marks_existing_previews_without_opt_in_uploads(migration_engine):
    from alembic import command
    from app.migrate import configuration,upgrade_schema
    from sqlalchemy import text
    with migration_engine.begin() as connection:
        command.upgrade(configuration(connection),'0022_excerpt_previews')
        connection.execute(text("INSERT INTO users (id,email,password_hash,created_at) VALUES ('owner','fixture@example.invalid','fixture',CURRENT_TIMESTAMP)"))
        for identity,parent in [('source',None),('preview','source')]:
            connection.execute(text("INSERT INTO render_jobs (id,user_id,title,style,desired_seconds,source_duration_seconds,source_path,status,attempt_count,created_at,preview_parent_id) VALUES (:id,'owner','Keep','vlog',15,12,'fixture','succeeded',1,CURRENT_TIMESTAMP,:parent)"),dict(id=identity,parent=parent))
    upgrade_schema(migration_engine)
    with migration_engine.connect() as connection:
        assert dict(connection.execute(text('SELECT id,operation FROM render_jobs')).all())=={'source':'render','preview':'preview'}


def test_pending_cancel_between_inventory_and_owner_lock_cannot_enqueue(client,automatic,monkeypatch):
    item=automatic
    with SessionLocal.begin() as db:db.scalar(select(UploadSession).where(UploadSession.job_id==item['jid'])).english_analysis=True
    from app.automatic_analysis import lock_owner as original_lock
    def cancelled_before_lock(db,owner,**kwargs):
        # Simulate the cancellation commit after the inventory read, before the
        # reconciliation owner transaction acquires its lock.
        db.execute(update(UploadSession).where(UploadSession.job_id==item['jid']).values(english_analysis=False))
        return original_lock(db,owner,**kwargs)
    monkeypatch.setattr('app.automatic_analysis.lock_owner',cancelled_before_lock)
    assert reconcile_requested()==0
    with SessionLocal() as db:
        assert db.scalar(select(RenderJob.id).where(RenderJob.preview_parent_id==item['jid'],RenderJob.operation=='analysis')) is None
