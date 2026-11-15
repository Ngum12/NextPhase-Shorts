"""Full-transcript mode, historical cache upgrade and private render admission."""
import json,uuid
import httpx
import pytest
from sqlalchemy import delete,select

from app.analysis_annotations import fingerprint
from app.config import get_settings
from app.db import SessionLocal
from app.models import ProjectAnalysis,RenderJob,AuthRateBucket
from app.passage_plan import WordRange
from app.story_planner import StorySelection,StoryPlannerUnavailable,plan_passages as provider_planner
from test_project_analysis import prepared,saved_payload
from test_gemini_selection import setup,request
from test_excerpt_jobs import actual


def body(item,**changes):
    return {**item['body'],'mode':'passages','consent_version':'gemini-passages-v1',**changes}


def passages(client,item,**changes):
    return client.post(item['url']+'/gemini-selection',headers=item['owner'],json=body(item,**changes))


@pytest.fixture
def planner(setup,monkeypatch):
    calls=[]
    def choose(transcript,base,**kwargs):
        calls.append(1)
        def answer(request):
            payload=json.loads(request.content)
            assert payload['generationConfig']['maxOutputTokens']==128
            return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[
                {'text':'{"clips":[{"first_unit":0,"last_unit":0}]}'}]}}]})
        with httpx.Client(transport=httpx.MockTransport(answer)) as client:
            return provider_planner(transcript,base,client=client,**kwargs)
    monkeypatch.setattr('app.story_planner.plan_passages',choose)
    return setup,calls


def test_full_source_passage_can_be_outside_shortlist_and_reuses_its_proof_for_captions_and_render(client,planner):
    p,calls=planner
    assert client.get(p['url'],headers=p['owner']).json()['gemini_passages_supported'] is True
    result=passages(client,p);assert result.status_code==200,result.text
    plan=result.json();assert plan['gemini_strategy']=='passages' and plan['gemini_candidate_count']==1
    first=plan['candidates'][0]
    assert (first['first_word'],first['last_word'])==(0,9)
    assert first not in p['base']['candidates']
    assert first['source_end_ms']==p['transcript'].words[9].end_ms
    assert passages(client,p,idempotency_key=str(uuid.uuid4())).json()==plan
    assert request(client,p).json()==plan  # Older app reuses the already-consented result.
    assert client.get(p['url']+'/automatic-clips?gemini=true',headers=p['owner']).json()==plan
    captions=client.get(p['url']+'/captions',headers=p['owner'],params={
        'revision':plan['revision'],'candidate_number':1,'automatic':True,'gemini':True})
    assert captions.status_code==200
    queued=client.post(p['url']+'/previews',headers=p['owner'],json=dict(
        revision=plan['revision'],candidate_number=1,idempotency_key=str(uuid.uuid4()),acknowledged_preview=True,
        automatic_draft=True,gemini_draft=True,caption_style='clean-1'))
    assert queued.status_code==202,queued.text
    with SessionLocal() as db:
        row=db.get(ProjectAnalysis,p['jid']);data=json.loads(row.gemini_selection_json)
        assert data['schema_version']=='gemini-selection-2' and data['word_ranges']==[{'first_word':0,'last_word':9}]
        assert 'word0' not in row.gemini_selection_json and row.review_json is None
        from app.excerpt_jobs import ExcerptSpec
        spec=ExcerptSpec.model_validate_json(db.get(RenderJob,queued.json()['id']).preview_spec_json)
        assert spec.gemini_strategy=='passages' and spec.source_end_ms==first['source_end_ms']
    assert calls==[1] and not p['calls']


def test_legacy_selection_upgrades_once_with_explicit_new_consent_and_old_render_replays(client,planner):
    p,calls=planner;old=request(client,p).json();key=str(uuid.uuid4())
    payload=dict(revision=old['revision'],candidate_number=1,idempotency_key=key,acknowledged_preview=True,
        automatic_draft=True,gemini_draft=True)
    existing=client.post(p['url']+'/previews',headers=p['owner'],json=payload);assert existing.status_code==202
    new=passages(client,p).json()
    assert new['revision']!=old['revision'] and new['gemini_strategy']=='passages'
    assert len(p['calls'])==len(calls)==1
    assert passages(client,p).json()==new and calls==[1]
    assert client.post(p['url']+'/previews',headers=p['owner'],json=payload).json()['id']==existing.json()['id']
    assert client.post(p['url']+'/previews',headers=p['owner'],json={**payload,'idempotency_key':str(uuid.uuid4())}).status_code==409


@pytest.mark.parametrize('changes',[
    {'consent_version':'gemini-transcript-v1'}, {'acknowledged_google_transcript_sharing':False},
    {'mode':'shortlist','consent_version':'gemini-passages-v1'}, {'mode':'unknown'},
    {'word_ranges':[{'first_word':0,'last_word':9}]},
])
def test_new_mode_cannot_bypass_consent_or_accept_client_supplied_ranges(client,planner,changes):
    p,calls=planner
    assert passages(client,p,**changes).status_code==422
    assert not calls
    with SessionLocal() as db:assert db.get(ProjectAnalysis,p['jid']).gemini_selection_json is None


@pytest.mark.parametrize('failure',['PROVIDER_RATE_LIMITED','OUTPUT_INVALID','MODEL_DECLINED'])
def test_passage_failure_keeps_standard_selector_and_is_not_resent(client,planner,monkeypatch,failure):
    p,calls=planner
    def fail(*a,**kw):calls.append(1);raise StoryPlannerUnavailable(failure)
    monkeypatch.setattr('app.story_planner.plan_passages',fail)
    result=passages(client,p).json()
    assert result['gemini_strategy']=='passages' and result['gemini_status']=='fallback'
    assert result['gemini_candidate_count']==0 and result['gemini_code']==failure
    assert result['candidates']==p['base']['candidates']
    assert passages(client,p).json()==result and len(calls)==1


def test_quota_denial_does_not_send_transcript(client,planner,monkeypatch):
    p,calls=planner;monkeypatch.setattr(get_settings(),'gemini_owner_daily_limit',0)
    result=passages(client,p).json()
    assert result['gemini_code']=='DAILY_LIMIT' and result['gemini_strategy']=='passages' and not calls


def test_deletion_during_passage_call_wins_over_late_result(client,planner,monkeypatch):
    p,calls=planner
    def remove(transcript,base,**kw):
        assert client.delete('/api/v1/jobs/'+p['jid'],headers=p['owner']).status_code==202
        return StorySelection(1,kw['model'],fingerprint(base),.1,1,1,(WordRange(first_word=0,last_word=9),))
    monkeypatch.setattr('app.story_planner.plan_passages',remove)
    assert passages(client,p).status_code==404
    with SessionLocal() as db:assert db.get(ProjectAnalysis,p['jid']) is None


def test_changed_review_fences_passage_result(client,planner,monkeypatch):
    p,calls=planner
    def change(transcript,base,**kw):
        assert client.put(p['url']+'/review',headers=p['owner'],json=saved_payload(client,p)).status_code==200
        return StorySelection(1,kw['model'],fingerprint(base),.1,1,1,(WordRange(first_word=0,last_word=9),))
    monkeypatch.setattr('app.story_planner.plan_passages',change)
    assert passages(client,p).status_code==409
    assert client.get(p['url']+'/automatic-clips?gemini=true',headers=p['owner']).status_code==409


def test_passage_mode_renders_real_synthetic_video_with_original_hash_and_no_word_edits(client,actual,monkeypatch):
    from app.worker import claim_job,process
    from app.local_transcription import file_digest
    s=get_settings()
    for name,value in [('gemini_planning_enabled',True),('gemini_free_tier_confirmed',True),('gemini_api_key','synthetic-key')]:monkeypatch.setattr(s,name,value)
    monkeypatch.setattr('app.story_planner.plan_passages',lambda transcript,base,**kw:StorySelection(
        1,kw['model'],fingerprint(base),.1,1,1,(WordRange(first_word=0,last_word=1),)))
    with SessionLocal.begin() as db:db.execute(delete(AuthRateBucket))
    base=client.get(actual['url']+'/automatic-clips',headers=actual['owner']).json()
    actual['body']={'revision':base['revision'],'idempotency_key':str(uuid.uuid4()),'acknowledged_google_transcript_sharing':True}
    plan=passages(client,actual).json();assert plan['gemini_strategy']=='passages'
    response=client.post(actual['url']+'/previews',headers=actual['owner'],json=dict(
        revision=plan['revision'],candidate_number=1,idempotency_key=str(uuid.uuid4()),acknowledged_preview=True,
        automatic_draft=True,gemini_draft=True,caption_style='clean-1'))
    assert response.status_code==202,response.text
    job=claim_job();assert job['id']==response.json()['id'];process(job)
    status=client.get('/api/v1/jobs/'+job['id'],headers=actual['owner']).json();assert status['status']=='succeeded',status
    assert client.get('/api/v1/jobs/'+job['id']+'/download',headers=actual['owner']).status_code==200
    assert file_digest(actual['source'])==actual['transcript'].source_sha256


def test_passage_upgrade_does_not_replace_an_inflight_legacy_claim(client,planner):
    import time
    from app.gemini_selection import Cached
    p,calls=planner
    value=Cached(base_plan_sha256=p['base']['revision'],request_id=uuid.uuid4(),status='pending',consent_at=int(time.time()))
    with SessionLocal.begin() as db:db.get(ProjectAnalysis,p['jid']).gemini_selection_json=value.model_dump_json()
    response=passages(client,p)
    assert response.status_code==202 and response.json()['gemini_status']=='pending' and not calls
    with SessionLocal() as db:
        assert json.loads(db.get(ProjectAnalysis,p['jid']).gemini_selection_json)['request_id']==str(value.request_id)


def test_corrupted_passage_proof_cannot_render_or_call_provider_again(client,planner):
    p,calls=planner;plan=passages(client,p).json();assert calls==[1]
    with SessionLocal.begin() as db:
        row=db.get(ProjectAnalysis,p['jid']);data=json.loads(row.gemini_selection_json)
        data['word_ranges'][0]['last_word']=999;row.gemini_selection_json=json.dumps(data)
    assert client.get(p['url']+'/automatic-clips?gemini=true',headers=p['owner']).status_code==409
    assert passages(client,p).status_code==409 and calls==[1]
