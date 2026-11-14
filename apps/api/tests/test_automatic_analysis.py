"""Analysis admission and publication fences; no real recognition claimed here."""
from datetime import timedelta
import uuid
import pytest
from sqlalchemy import select,update
from app.config import get_settings
from app.db import SessionLocal
from app.models import RenderJob,RenderAttempt,UploadSession,ProjectAnalysis,utcnow
from app.automatic_analysis import publish,reconcile_requested
from app.asr_failures import TIMING_CODES
from test_project_analysis import prepared,imported,saved_payload
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


def test_analysis_claim_covers_longer_visual_scan_and_still_expires(client,automatic,monkeypatch):
    from app import worker,broker
    from app.analysis_limits import VISUAL_TIMEOUT_SECONDS
    from app.job_supervision import renew_claim
    child=start(client,automatic).json()['task']['id']
    # The prepared source fixture need not be processed to claim its analysis.
    with SessionLocal.begin() as db:
        db.get(RenderJob,automatic['jid']).status='succeeded'
    began=utcnow()
    monkeypatch.setattr(worker,'utcnow',lambda:began)
    job=worker.claim_job()
    assert job['id']==child
    with SessionLocal() as db:
        row=db.get(RenderJob,child)
        deadline=broker.aware(row.claim_deadline_at)
        assert (deadline-began).total_seconds()==get_settings().english_analysis_timeout_seconds+VISUAL_TIMEOUT_SECONDS+180
        assert broker.aware(db.get(RenderAttempt,job['claim_token']).deadline_at)==deadline
    # Renewals cannot make this expanded allowance unbounded.
    monkeypatch.setattr('app.job_supervision.utcnow',lambda:deadline+timedelta(seconds=1))
    assert not renew_claim(job)

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
@pytest.mark.parametrize('timing',['zero_width','terminal_overrun'])
def test_worker_pipeline_copies_hashes_decodes_and_cleans_attempt(client,monkeypatch,tmp_path,visual_available,timing):
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
    if timing=='terminal_overrun':
        duration=item['transcript'].source_duration_ms
        data['transcription'][0]['tokens'][0]['offsets']={'from':duration-25,'to':duration+135}
        data['transcription'][0]['tokens'][1]['offsets']={'from':duration-10,'to':duration}
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
    if timing=='terminal_overrun':
        assert document['transcript']['words'][0]['end_ms']==duration
        assert document['transcript']['words'][0]['start_ms']==duration-25
        assert document['transcript']['words'][0]['confidence']==.9
    assert 'adjusted_word_timestamps' in document['proposal']['warnings']
    assert document['review'] is None and not document['render_enabled']
    assert document['proposal']['human_review_required']
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


@pytest.mark.parametrize('code',sorted(TIMING_CODES))
def test_failed_asr_category_is_durable_and_owner_only(client,automatic,monkeypatch,code):
    from app import worker
    from app.asr_failures import AsrFailure
    child=start(client,automatic).json()['task']['id']
    with SessionLocal.begin() as db:
        db.get(RenderJob,automatic['jid']).status='succeeded'
    job=worker.claim_job()
    assert job['id']==child

    def simulated_failure(*args,**kwargs):
        raise AsrFailure(code)

    monkeypatch.setattr('app.analysis_work.process_analysis',simulated_failure)
    worker.process(job)
    state=client.get(automatic['auto'],headers=automatic['owner'])
    assert state.status_code==200
    assert state.json()['task']['error_code']==code
    assert state.json()['task']['status']=='failed'
    assert client.get(automatic['auto'],headers=automatic['other']).status_code==404
    with SessionLocal() as db:
        saved=db.get(RenderJob,child)
        assert saved.error_code==code


def terminal_transcript(item):
    """Parsed synthetic estimate bound to this accepted upload's identity."""
    from app.local_transcription import parse_whisper
    source=item['transcript']
    duration=source.source_duration_ms
    data={'params':{'translate':False},'result':{'language':'en'},
        'model':{'multilingual':True,'vocab':51865},'transcription':[{
            'text':' Ending.', 'tokens':[{'text':' Ending.','id':100,'p':.9,
                'offsets':{'from':duration-25,'to':duration+135}}]}]}
    return parse_whisper(data,source_sha256=source.source_sha256,source_duration_ms=duration,
        language='en',model_sha256='b'*64,engine_sha256='c'*64)


@pytest.mark.parametrize('fence',['cancel','lease','deadline','claim','delete'])
def test_corrected_terminal_transcript_cannot_bypass_publication_fences(client,automatic,fence):
    item=automatic;child=start(client,item).json()['task']['id'];job=claimed(child)
    transcript=terminal_transcript(item)
    assert transcript.timestamp_quality=='model_token_estimate_adjusted'
    if fence=='cancel':
        assert client.post(item['auto']+'/cancel',headers=item['owner']).status_code==200
    elif fence=='delete':
        assert client.delete('/api/v1/jobs/'+item['jid'],headers=item['owner']).status_code==202
    else:
        with SessionLocal.begin() as db:
            row=db.get(RenderJob,child)
            if fence=='lease':row.lease_expires_at=utcnow()-timedelta(seconds=1)
            elif fence=='deadline':row.claim_deadline_at=utcnow()-timedelta(seconds=1)
            else:row.claim_token=str(uuid.uuid4())
    assert not publish(job,transcript,1)
    with SessionLocal() as db:assert db.get(ProjectAnalysis,item['jid']) is None


def test_failed_analysis_retry_reuses_retained_upload_and_keeps_old_failure(client,automatic):
    from pathlib import Path
    from app.worker import mark_done
    item=automatic;child=start(client,item).json()['task']['id'];job=claimed(child)
    with SessionLocal() as db:
        source=Path(db.get(RenderJob,item['jid']).source_path)
        original=source.read_bytes()
        upload=db.scalar(select(UploadSession).where(UploadSession.job_id==item['jid']))
        upload_id=upload.id
    assert mark_done(child,job['claim_token'],error_code='ASR_OFFSETS_OUT_OF_SOURCE')
    retry=start(client,item,child,retry_failed=True)
    assert retry.status_code==202 and retry.json()['task']['id']!=child
    next_id=retry.json()['task']['id']
    assert start(client,item,child,retry_failed=True).json()['task']['id']==next_id
    assert publish(claimed(next_id),terminal_transcript(item),1)
    state=client.get(item['auto'],headers=item['owner']).json()
    assert state['ready'] and state['task']['id']==next_id
    doc=client.get(item['url'],headers=item['owner']).json()
    assert doc['transcript']['timestamp_quality']=='model_token_estimate_adjusted'
    assert 'adjusted_word_timestamps' in doc['proposal']['warnings']
    assert doc['review'] is None and not doc['render_enabled']
    assert source.read_bytes()==original
    with SessionLocal() as db:
        assert db.get(RenderJob,child).error_code=='ASR_OFFSETS_OUT_OF_SOURCE'
        assert db.get(UploadSession,upload_id).status=='completed'


def test_corrected_analysis_never_overwrites_existing_review(client,automatic):
    item=automatic;child=start(client,item).json()['task']['id'];job=claimed(child)
    imported(item)
    assert client.put(item['url']+'/review',headers=item['owner'],json=saved_payload(client,item)).status_code==200
    before=client.get(item['url'],headers=item['owner']).json()
    assert publish(job,terminal_transcript(item),1)
    assert client.get(item['url'],headers=item['owner']).json()==before
    assert start(client,item,retry_failed=True).json()['ready']
    assert client.get(item['url'],headers=item['owner']).json()==before
