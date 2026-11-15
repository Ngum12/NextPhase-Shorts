"""API -> leased worker -> real native output; no provider/private media traffic."""
import json,subprocess
from datetime import timedelta,datetime,timezone
from pathlib import Path
import pytest
from sqlalchemy import select,func,update
from app.config import get_settings
from app.db import SessionLocal
from app.models import RenderJob,ProjectAnalysis,AuthRateBucket,utcnow
from app.documentary_jobs import DocumentarySpec,checkpoint,CONSENT
from app.documentary_director import Direction,VisualChoice,headings,direct,select_visuals
from app.documentary_plan import DocumentaryFailure,AssetReceipt
from app.documentary_render import checksum
from app.media import MediaCancelled
from test_project_analysis import prepared,imported
from test_excerpt_jobs import actual

BODY={'consent_version':CONSENT,'acknowledged_google_transcript_sharing':True,'acknowledged_public_research':True}


def enable(monkeypatch):
    settings=get_settings()
    for name,value in [('gemini_planning_enabled',True),('gemini_free_tier_confirmed',True),
                       ('gemini_api_key','synthetic-test-key'),('english_analysis_enabled',True)]:
        monkeypatch.setattr(settings,name,value)


def queue(client,item,body=None,headers=None):
    return client.post(item['url']+'/documentary',headers=headers or item['owner'],json=BODY if body is None else body)


def test_admission_requires_both_consents_owner_analysis_and_free_tier(client,prepared,monkeypatch):
    enable(monkeypatch)
    assert queue(client,prepared).status_code==409
    imported(prepared)
    assert queue(client,prepared,headers=prepared['other']).status_code==404
    assert client.post(prepared['url']+'/documentary',json=BODY).status_code==401
    for field in ['acknowledged_google_transcript_sharing','acknowledged_public_research']:
        bad=queue(client,prepared,{**BODY,field:False,'private':'Never reflect this text'})
        assert bad.status_code==422 and 'Never reflect' not in bad.text
    monkeypatch.setattr(get_settings(),'gemini_free_tier_confirmed',False)
    assert queue(client,prepared).status_code==409
    monkeypatch.setattr(get_settings(),'gemini_free_tier_confirmed',True)
    assert client.get('/api/v1/english-analysis/capabilities',headers=prepared['owner']).json()['documentary_available']


def test_one_admission_reserves_all_scratch_and_two_calls_without_transcript_copy(client,prepared,monkeypatch):
    enable(monkeypatch);imported(prepared)
    first=queue(client,prepared);assert first.status_code==202,first.text
    assert first.json()['documentary'] and first.json()['style']=='documentary'
    assert queue(client,prepared).json()['id']==first.json()['id']
    with SessionLocal() as db:
        row=db.get(RenderJob,first.json()['id']);spec=DocumentarySpec.model_validate_json(row.preview_spec_json)
        assert row.storage_reserved_bytes==2*(2*spec.source_bytes+129*1024**2+row.max_render_bytes)
        assert spec.consent_version==CONSENT and not spec.direction_started and not spec.visuals_started
        assert 'word0' not in row.preview_spec_json and spec.transcript_sha256
        assert db.get(ProjectAnalysis,prepared['jid']).review_json is None
    assert client.delete('/api/v1/jobs/'+first.json()['id'],headers=prepared['owner']).status_code==202
    assert queue(client,prepared).status_code==410


def test_daily_budget_and_capacity_fail_before_job_or_provider(client,prepared,monkeypatch):
    enable(monkeypatch);imported(prepared)
    monkeypatch.setattr(get_settings(),'gemini_owner_daily_limit',1)
    assert queue(client,prepared).status_code==429
    monkeypatch.setattr(get_settings(),'gemini_owner_daily_limit',5)
    monkeypatch.setattr(get_settings(),'account_storage_bytes',1)
    assert queue(client,prepared).status_code==409
    with SessionLocal() as db:
        assert not db.scalar(select(RenderJob.id).where(RenderJob.idempotency_key=='documentary_'+prepared['jid']))


def test_checkpoint_refuses_cancelled_deleted_expired_and_replaced_claims(client,prepared,monkeypatch):
    enable(monkeypatch);imported(prepared);child=queue(client,prepared).json()['id'];token='synthetic-claim'
    with SessionLocal.begin() as db:
        row=db.get(RenderJob,child);row.status='processing';row.claim_token=token
        row.lease_expires_at=utcnow()+timedelta(minutes=1);row.claim_deadline_at=utcnow()+timedelta(minutes=2)
    job={'id':child,'claim_token':token,'user_id':prepared['uid'],'preview_parent_id':prepared['jid']}
    assert not checkpoint(job,lambda s:s).direction_started
    with pytest.raises(MediaCancelled):checkpoint({**job,'claim_token':'other'},lambda s:s)
    with SessionLocal.begin() as db:db.get(RenderJob,child).lease_expires_at=utcnow()-timedelta(seconds=1)
    with pytest.raises(MediaCancelled):checkpoint(job,lambda s:s)
    assert client.delete('/api/v1/jobs/'+prepared['jid'],headers=prepared['owner']).status_code==202
    with pytest.raises(MediaCancelled):checkpoint(job,lambda s:s)


def direction(words):
    return Direction(public_query='Moon',opening_first=0,opening_last=0,
        closing_first=len(words)-1,closing_last=len(words)-1,motion='push_in')


def mock_providers(monkeypatch,tmp_path,calls):
    import app.documentary_work as work
    usage={'wall_ms':1,'input_tokens':10,'output_tokens':10}
    def plan(words,**kw):calls.append('direction');return direction(words),usage
    def choose(words,candidates,**kw):calls.append('visuals');return VisualChoice(first=1,second=0),usage
    monkeypatch.setattr(work,'direct',plan);monkeypatch.setattr(work,'select_visuals',choose)
    image=tmp_path/'asset.jpg'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=teal:s=320x240','-frames:v','1',str(image)],
        check=True,timeout=30)
    receipt=AssetReceipt(asset_id=checksum(image),kind='image',origin='commons',creator='Synthetic public-source fixture',
        title='Synthetic Moon fixture',license='public-domain',source_url='https://commons.wikimedia.org/wiki/File:Fixture.jpg',
        download_url='https://upload.wikimedia.org/wikipedia/commons/a/ab/Fixture.jpg',
        retrieved_at=datetime.now(timezone.utc).isoformat(),bytes=image.stat().st_size)
    class Research:
        def __init__(self,*,consented):assert consented
        def search_context(self,query):calls.append('context');return []
        def search(self,query,*,kind):calls.append('search');return [{'title':receipt.title,'creator':receipt.creator}]
        def download(self,candidate,root):calls.append('download');return receipt,image
        def close(self):pass
    monkeypatch.setattr(work,'CommonsResearch',Research)


def test_uploaded_project_to_documentary_download_provenance_and_deletion(client,actual,monkeypatch,tmp_path,caplog):
    enable(monkeypatch);calls=[];mock_providers(monkeypatch,tmp_path,calls)
    response=queue(client,actual);assert response.status_code==202,response.text
    child=response.json()['id']
    from app.worker import claim_job,process
    job=claim_job();assert job['id']==child
    process(job)
    result=client.get('/api/v1/jobs/'+child,headers=actual['owner']).json()
    assert result['status']=='succeeded',result
    assert result['documentary'] and result['output_duration_seconds']<=5.01
    media=client.get('/api/v1/jobs/'+child+'/download',headers=actual['owner']);assert media.status_code==200 and len(media.content)>1000
    sources=client.get('/api/v1/jobs/'+child+'/documentary-sources',headers=actual['owner'])
    assert sources.status_code==200 and sources.json()['assets'][0]['creator']=='Synthetic public-source fixture'
    assert not sources.json()['claims_verified']
    assert calls==['direction','context','search','visuals','download']
    assert queue(client,actual).json()['id']==child and len(calls)==5
    with SessionLocal() as db:
        row=db.get(RenderJob,child);root=Path(row.output_path).parent
        assert not list(root.glob('research-*')) and not [p for p in root.glob('documentary-*') if p.is_dir()] and not (root/'input.media').exists()
        assert actual['source'].exists()
        spec=DocumentarySpec.model_validate_json(row.preview_spec_json);assert len(spec.usage)==2
    assert 'Original speech.' not in caplog.text
    assert client.delete('/api/v1/jobs/'+actual['jid'],headers=actual['owner']).status_code==202
    assert client.get('/api/v1/jobs/'+child+'/download',headers=actual['owner']).status_code==404
    assert client.get('/api/v1/jobs/'+child+'/documentary-sources',headers=actual['owner']).status_code==404


def test_interrupted_provider_is_never_repeated_after_queue_recovery(client,actual,monkeypatch,tmp_path):
    enable(monkeypatch);calls=[];mock_providers(monkeypatch,tmp_path,calls)
    child=queue(client,actual).json()['id']
    from app.worker import claim_job,process
    with SessionLocal.begin() as db:
        row=db.get(RenderJob,child);data=json.loads(row.preview_spec_json);data['direction_started']=True;row.preview_spec_json=json.dumps(data)
    job=claim_job();process(job)
    result=client.get('/api/v1/jobs/'+child,headers=actual['owner']).json()
    assert result['status']=='failed' and result['error_code']=='DOCUMENTARY_PLAN_INVALID'
    assert calls==[]
    assert queue(client,actual).json()['id']==child


def test_deletion_during_direction_revokes_result_and_stops_research(client,actual,monkeypatch):
    enable(monkeypatch);queue(client,actual)
    import app.documentary_work as work
    def delete_during(words,**kwargs):
        assert client.delete('/api/v1/jobs/'+actual['jid'],headers=actual['owner']).status_code==202
        return direction(words),{'wall_ms':1,'input_tokens':1,'output_tokens':1}
    monkeypatch.setattr(work,'direct',delete_during)
    monkeypatch.setattr(work,'CommonsResearch',lambda **kw:pytest.fail('No research after source deletion'))
    from app.worker import claim_job,process
    job=claim_job();process(job)
    assert client.get('/api/v1/jobs/'+job['id'],headers=actual['owner']).status_code==404


def test_heading_contract_cannot_invent_text_or_execute_motion():
    value=direction(['A','public','topic.']);assert headings(value,['A','public','topic.'])==['A','topic.']
    with pytest.raises(ValueError):headings(value,['A'])
    with pytest.raises(ValueError):Direction.model_validate({**value.model_dump(),'motion':'shell'})


def provider_client(payload,requests):
    import httpx
    def answer(request):
        requests.append(request)
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(payload)}]}}],
            'usageMetadata':{'promptTokenCount':12,'candidatesTokenCount':20}})
    return httpx.Client(transport=httpx.MockTransport(answer))


def test_director_uses_closed_schema_bounded_output_and_exact_spoken_headings(caplog):
    requests=[];words=['Synthetic','public','Moon','story.'];value=direction(words)
    with provider_client(value.model_dump(),requests) as client:
        planned,usage=direct(words,api_key='synthetic-key',model='gemini-3.1-flash-lite',client=client)
    assert headings(planned,words)==['Synthetic','story.'] and usage['input_tokens']==12
    body=json.loads(requests[0].content)
    assert body['generationConfig']['maxOutputTokens']==512
    assert body['generationConfig']['responseSchema']['type']=='OBJECT'
    assert not requests[0].url.query and requests[0].headers['x-goog-api-key']=='synthetic-key'
    assert 'Synthetic public Moon story.' not in caplog.text and 'synthetic-key' not in caplog.text


@pytest.mark.parametrize('first,second',[(0,0),(9,1),(1,9)])
def test_visual_director_declines_unrelated_or_unknown_assets_without_raw_output(first,second,caplog):
    from app.story_planner import StoryPlannerUnavailable
    with provider_client({'first':first,'second':second},[]) as client:
        with pytest.raises(StoryPlannerUnavailable) as error:
            select_visuals(['Synthetic','speech'],[{'title':'Public fixture','creator':'Author'}],
                api_key='synthetic-key',model='gemini-3.1-flash-lite',client=client)
    assert error.value.code in ('MODEL_DECLINED','OUTPUT_INVALID') and 'Public fixture' not in caplog.text


def test_research_failure_is_terminal_and_reopening_never_repeats_planning(client,actual,monkeypatch,tmp_path):
    enable(monkeypatch);calls=[];mock_providers(monkeypatch,tmp_path,calls)
    import app.documentary_work as work
    class FailedResearch:
        def __init__(self,**kwargs):pass
        def search_context(self,query):calls.append('unavailable');raise DocumentaryFailure('RESEARCH_UNAVAILABLE')
        def close(self):pass
    monkeypatch.setattr(work,'CommonsResearch',FailedResearch)
    child=queue(client,actual).json()['id']
    from app.worker import claim_job,process
    process(claim_job())
    result=client.get('/api/v1/jobs/'+child,headers=actual['owner']).json()
    assert result['status']=='failed' and result['error_code']=='DOCUMENTARY_RESEARCH_UNAVAILABLE'
    assert queue(client,actual).json()['id']==child and calls==['direction','unavailable']
    assert client.get('/api/v1/jobs/'+child+'/documentary-sources',headers=actual['owner']).status_code==404


def test_budget_pause_and_foreign_sources_do_not_leak_or_admit(client,prepared,monkeypatch):
    enable(monkeypatch);imported(prepared)
    from fastapi import HTTPException
    def pause():raise HTTPException(503,'Paused by operator')
    monkeypatch.setattr('app.budget_control.require_open',pause)
    assert queue(client,prepared).status_code==503
    assert client.get('/api/v1/jobs/'+prepared['jid']+'/documentary-sources',headers=prepared['other']).status_code==404
