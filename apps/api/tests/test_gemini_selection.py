"""Synthetic source data only; no real credentials or provider calls."""
import uuid

import pytest
from sqlalchemy import select,delete

from app.analysis_annotations import fingerprint
from app.config import get_settings
from app.db import SessionLocal
from app.models import ProjectAnalysis,RenderJob,AuthRateBucket
from app.story_planner import StorySelection,StoryPlannerUnavailable
from test_project_analysis import prepared,imported,saved_payload
from test_excerpt_jobs import actual
from test_migrations import migration_engine


@pytest.fixture
def setup(client,prepared,monkeypatch):
    imported(prepared)
    s=get_settings()
    monkeypatch.setattr(s,'gemini_planning_enabled',True)
    monkeypatch.setattr(s,'gemini_free_tier_confirmed',True)
    monkeypatch.setattr(s,'gemini_api_key','synthetic-test-key')
    # Isolate request budgets; no external calls in this test process.
    with SessionLocal.begin() as db:db.execute(delete(AuthRateBucket))
    plan=client.get(prepared['url']+'/automatic-clips',headers=prepared['owner']).json()
    prepared['base']=plan
    prepared['body']=dict(revision=plan['revision'],idempotency_key=str(uuid.uuid4()),
        consent_version='gemini-transcript-v1',acknowledged_google_transcript_sharing=True)
    prepared['calls']=[]
    def choose(transcript,plan,**kwargs):
        prepared['calls'].append(fingerprint(plan))
        return StorySelection(len(plan.candidates),kwargs['model'],fingerprint(plan),.1,300,8)
    monkeypatch.setattr('app.story_planner.select',choose)
    return prepared


def request(client,item,**changes):
    return client.post(item['url']+'/gemini-selection',headers=item['owner'],json={**item['body'],**changes})


def test_consent_ownership_and_disabled_feature_never_call_provider(client,setup,monkeypatch):
    p=setup;url=p['url']+'/gemini-selection'
    assert request(client,p,acknowledged_google_transcript_sharing=False).status_code==422
    assert request(client,p,acknowledged_google_transcript_sharing='true').status_code==422
    assert request(client,p,consent_version='other').status_code==422
    assert client.post(url,json=p['body']).status_code==401
    assert client.post(url,headers=p['other'],json=p['body']).status_code==404
    assert request(client,p,revision='0'*64).status_code==409
    monkeypatch.setattr(get_settings(),'gemini_free_tier_confirmed',False)
    assert request(client,p).status_code==409
    assert not p['calls']
    with SessionLocal() as db:assert db.get(ProjectAnalysis,p['jid']).gemini_selection_json is None


def test_cached_selection_reorders_only_known_ranges_and_caption_render_reuse_it(client,setup):
    p=setup;base=p['base'];response=request(client,p)
    assert response.status_code==200,response.text
    assert response.headers['cache-control']=='private, no-store'
    result=response.json();assert result['gemini_status']=='selected'
    assert result['candidates'][0]==base['candidates'][-1]
    assert sorted(c['first_word'] for c in result['candidates'])==sorted(c['first_word'] for c in base['candidates'])
    assert result['revision']!=base['revision']
    assert request(client,p,idempotency_key=str(uuid.uuid4())).json()==result
    assert client.get(p['url']+'/gemini-selection',headers=p['owner']).json()==result
    assert client.get(p['url']+'/automatic-clips?gemini=true',headers=p['owner']).json()==result
    assert client.get(p['url']+'/automatic-clips',headers=p['owner']).json()==base
    caption=client.get(p['url']+'/captions',headers=p['owner'],params={
        'revision':result['revision'],'candidate_number':1,'automatic':True,'gemini':True})
    assert caption.status_code==200
    body=dict(revision=result['revision'],candidate_number=1,idempotency_key=str(uuid.uuid4()),
        acknowledged_preview=True,automatic_draft=True,gemini_draft=True,caption_style='clean-1')
    queued=client.post(p['url']+'/previews',headers=p['owner'],json=body)
    assert queued.status_code==202,queued.text
    assert client.post(p['url']+'/previews',headers=p['owner'],json=body).json()['id']==queued.json()['id']
    assert client.post(p['url']+'/previews',headers=p['owner'],json={**body,'gemini_draft':False}).status_code==409
    assert client.post(p['url']+'/previews',headers=p['owner'],json={**body,'automatic_draft':False}).status_code==422
    with SessionLocal() as db:
        row=db.get(ProjectAnalysis,p['jid'])
        assert row.review_json is None
        assert row.transcript_json==p['transcript'].model_dump_json()
        assert 'word0' not in row.gemini_selection_json and 'synthetic-test-key' not in row.gemini_selection_json
        from app.excerpt_jobs import ExcerptSpec
        spec=ExcerptSpec.model_validate_json(db.get(RenderJob,queued.json()['id']).preview_spec_json)
        assert spec.source_start_ms==result['candidates'][0]['source_start_ms']
        assert spec.review_revision==result['revision'] and spec.review_sha256 is None
        assert spec.gemini_model=='gemini-3.1-flash-lite' and spec.gemini_status=='selected'
    assert len(p['calls'])==1


@pytest.mark.parametrize('code',sorted(StoryPlannerUnavailable.CODES))
def test_fixed_provider_failure_falls_back_and_is_not_retried(client,setup,monkeypatch,code,caplog):
    calls=[]
    def fail(*a,**kw):calls.append(1);raise StoryPlannerUnavailable(code)
    monkeypatch.setattr('app.story_planner.select',fail)
    first=request(client,setup).json()
    assert first['gemini_status']=='fallback' and first['gemini_code']==code
    assert first['candidates']==setup['base']['candidates']
    assert request(client,setup).json()==first and len(calls)==1
    assert 'word0' not in caplog.text and 'synthetic-test-key' not in caplog.text


def test_budget_denial_is_cached_and_does_not_contact_google(client,setup,monkeypatch):
    monkeypatch.setattr(get_settings(),'gemini_owner_daily_limit',0)
    result=request(client,setup).json()
    assert result['gemini_code']=='DAILY_LIMIT'
    assert result['candidates']==setup['base']['candidates'] and not setup['calls']


def test_budget_is_atomic_per_owner_and_global_and_rolls_to_next_day(setup,monkeypatch):
    from app.gemini_selection import budget
    from app.models import utcnow
    from datetime import timedelta
    s=get_settings();monkeypatch.setattr(s,'gemini_owner_daily_limit',2);monkeypatch.setattr(s,'gemini_daily_limit',3)
    with SessionLocal.begin() as db:
        assert budget(db,'one');db.flush()
        assert budget(db,'one');db.flush()
        assert not budget(db,'one');assert budget(db,'two');db.flush()
        assert not budget(db,'three')
    tomorrow=utcnow()+timedelta(days=1)
    monkeypatch.setattr('app.gemini_selection.utcnow',lambda:tomorrow)
    with SessionLocal.begin() as db:assert budget(db,'one')


def test_pending_claim_is_reused_and_expired_claim_is_not_resent(client,setup):
    from app.gemini_selection import Cached
    import time
    p=setup
    value=Cached(base_plan_sha256=p['base']['revision'],request_id=uuid.uuid4(),status='pending',consent_at=int(time.time()))
    with SessionLocal.begin() as db:db.get(ProjectAnalysis,p['jid']).gemini_selection_json=value.model_dump_json()
    assert request(client,p).status_code==202
    with SessionLocal.begin() as db:db.get(ProjectAnalysis,p['jid']).gemini_selection_json=value.model_copy(update={'consent_at':int(time.time())-91}).model_dump_json()
    assert request(client,p).json()['gemini_code']=='PENDING_EXPIRED'
    assert not p['calls']


def test_deletion_during_call_discards_result_and_never_recreates_metadata(client,setup,monkeypatch):
    def remove(*a,**kw):
        assert client.delete('/api/v1/jobs/'+setup['jid'],headers=setup['owner']).status_code==202
        return StorySelection(1,'gemini-3.1-flash-lite',setup['base']['revision'],.1,1,1)
    monkeypatch.setattr('app.story_planner.select',remove)
    assert request(client,setup).status_code==404
    with SessionLocal() as db:assert db.get(ProjectAnalysis,setup['jid']) is None


def test_changed_analysis_rejects_late_response_and_old_render_revision(client,setup,monkeypatch):
    def change(*a,**kw):
        assert client.put(setup['url']+'/review',headers=setup['owner'],json=saved_payload(client,setup)).status_code==200
        return StorySelection(1,'gemini-3.1-flash-lite',setup['base']['revision'],.1,1,1)
    monkeypatch.setattr('app.story_planner.select',change)
    assert request(client,setup).status_code==409
    assert client.get(setup['url']+'/automatic-clips?gemini=true',headers=setup['owner']).status_code==409


def test_gemini_selected_excerpt_renders_and_downloads_real_synthetic_video(client,actual,monkeypatch,tmp_path):
    from app.worker import claim_job,process
    from app.local_transcription import file_digest
    from app.media import probe_video
    s=get_settings()
    for k,v in [('gemini_planning_enabled',True),('gemini_free_tier_confirmed',True),('gemini_api_key','synthetic-test-key')]:monkeypatch.setattr(s,k,v)
    monkeypatch.setattr('app.story_planner.select',lambda transcript,plan,**kw:StorySelection(1,kw['model'],fingerprint(plan),.1,1,1))
    with SessionLocal.begin() as db:db.execute(delete(AuthRateBucket))
    plan=client.get(actual['url']+'/automatic-clips',headers=actual['owner']).json()
    body=dict(revision=plan['revision'],idempotency_key=str(uuid.uuid4()),consent_version='gemini-transcript-v1',acknowledged_google_transcript_sharing=True)
    chosen=client.post(actual['url']+'/gemini-selection',headers=actual['owner'],json=body).json()
    result=client.post(actual['url']+'/previews',headers=actual['owner'],json=dict(
        revision=chosen['revision'],candidate_number=1,idempotency_key=str(uuid.uuid4()),acknowledged_preview=True,
        automatic_draft=True,gemini_draft=True,caption_style='clean-1',polish={}))
    assert result.status_code==202,result.text
    job=claim_job();assert job['id']==result.json()['id'];process(job)
    status=client.get('/api/v1/jobs/'+job['id'],headers=actual['owner']).json()
    assert status['status']=='succeeded',status
    response=client.get('/api/v1/jobs/'+job['id']+'/download',headers=actual['owner']);assert response.status_code==200
    path=tmp_path/'gemini.mp4';path.write_bytes(response.content);metadata=probe_video(path)
    assert (metadata['width'],metadata['height'])==(1080,1920) and metadata['duration']<=60
    assert file_digest(actual['source'])==actual['transcript'].source_sha256


def test_migration_preserves_existing_analysis_without_enabling_gemini(migration_engine):
    from alembic import command
    from app.migrate import configuration,upgrade_schema
    from app.models import User
    from sqlalchemy import text
    with migration_engine.begin() as connection:
        command.upgrade(configuration(connection),'0025_scene_analysis')
        connection.execute(User.__table__.insert().values(id='owner',email='fixture@example.invalid',password_hash='fixture'))
        connection.execute(RenderJob.__table__.insert().values(id='source',user_id='owner',title='Keep',style='vlog',
            desired_seconds=15,source_duration_seconds=5,source_path='fixture',status='cancelled'))
        connection.execute(text("INSERT INTO project_analyses (job_id,transcript_json,proposal_json,review_json,revision,created_at,updated_at) VALUES ('source','keep-text','keep-plan','keep-review',:revision,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),{'revision':'a'*64})
    upgrade_schema(migration_engine)
    with migration_engine.connect() as connection:
        row=connection.execute(text('SELECT transcript_json,review_json,revision,gemini_selection_json FROM project_analyses')).one()
        assert tuple(row)==('keep-text','keep-review','a'*64,None)


@pytest.mark.parametrize('raw',['{}','x'*4097,'{"status":"selected","candidate_id":99}'])
def test_corrupt_cache_cannot_select_or_render_a_clip(client,setup,raw):
    with SessionLocal.begin() as db:db.get(ProjectAnalysis,setup['jid']).gemini_selection_json=raw
    assert request(client,setup).status_code==409
    assert client.get(setup['url']+'/automatic-clips?gemini=true',headers=setup['owner']).status_code==409
    assert not setup['calls']


def test_concurrent_requests_share_one_claim_without_holding_sql_locks_during_provider_io(client,setup,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    began=threading.Event();release=threading.Event();calls=[]
    def choose(transcript,plan,**kw):
        calls.append(1);began.set()
        assert release.wait(5)
        return StorySelection(1,kw['model'],fingerprint(plan),.1,1,1)
    monkeypatch.setattr('app.story_planner.select',choose)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(request,client,setup)
        assert began.wait(5)
        try:
            # This must complete before provider I/O is released.
            second=pool.submit(request,client,setup,idempotency_key=str(uuid.uuid4())).result(timeout=3)
            assert second.status_code==202 and second.json()['gemini_status']=='pending'
        finally:release.set()
        assert first.result(timeout=5).json()['gemini_status']=='selected'
    assert calls==[1]
    with SessionLocal() as db:assert sum(row.attempts for row in db.scalars(select(AuthRateBucket)))==2


def test_emergency_budget_pause_blocks_new_provider_calls_without_consuming_a_request(client,setup,monkeypatch):
    from fastapi import HTTPException
    def paused():raise HTTPException(503,'Application admission is paused')
    monkeypatch.setattr('app.budget_control.require_open',paused)
    assert request(client,setup).status_code==503
    assert not setup['calls']
    with SessionLocal() as db:
        assert db.get(ProjectAnalysis,setup['jid']).gemini_selection_json is None
        assert list(db.scalars(select(AuthRateBucket)))==[]
