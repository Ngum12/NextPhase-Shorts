"""Automatic draft selection, owner-bound rendering and legacy review isolation."""
from datetime import timedelta
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.analysis_annotations import fingerprint
from app.analysis_plan import Transcript, Word
from app.automatic_clips import suggest
from app.db import SessionLocal
from app.excerpt_jobs import ExcerptSpec
from app.models import ProjectAnalysis, RenderJob, utcnow
from app.project_analysis import import_transcript
from test_project_analysis import prepared, imported, saved_payload
from test_excerpt_jobs import actual


def transcript(sentences,*,gap=0,confidence=.95):
    words=[];cursor=0
    for sentence in sentences:
        for text in sentence.split():
            words.append(Word(text=text,start_ms=cursor,end_ms=cursor+650,confidence=confidence))
            cursor+=750
        cursor+=gap
    return Transcript(source_sha256='a'*64,source_duration_ms=max(1,cursor),language='en',
        provider='whisper_cpp',model_sha256='b'*64,engine_sha256='c'*64,
        timestamp_quality='model_token_estimate',words=tuple(words))


def test_unpunctuated_speech_produces_source_bound_options_without_annotations():
    source=transcript([' '.join(['Speech']*100)])
    original=source.model_dump_json()
    result=suggest(source,15,'d'*64)
    assert result.candidates and len(result.candidates)<=5
    assert 'word_boundary_fallback' in result.warnings
    assert len({c.source_start_ms for c in result.candidates})>1
    assert result==suggest(source,15,'d'*64)
    assert source.model_dump_json()==original
    assert result.review_sha256 is None and result.semantic_quality_verified is False
    for c in result.candidates:
        assert c.source_start_ms==source.words[c.first_word].start_ms
        assert c.source_end_ms==source.words[c.last_word].end_ms
        assert 0<c.source_end_ms-c.source_start_ms<=15000
        assert c.output_frames==(c.source_end_ms-c.source_start_ms)*30//1000


def test_question_with_followup_outranks_question_only():
    source=transcript(['Why does this simple approach fail for so many people?',
        'The solution is to measure results before changing your approach.'])
    plan=suggest(source,30,'d'*64)
    assert plan.candidates
    best=plan.candidates[0]
    assert source.words[best.last_word].text=='approach.'
    assert best.first_word==0


def test_self_contained_later_question_and_answer_beat_dependent_opening():
    source=transcript(['But they wanted this because it was about something earlier.',
        'Why does this simple approach fail for so many people?',
        'The solution is to measure results before changing your approach.'])
    best=suggest(source,30,'d'*64).candidates[0]
    assert source.words[best.first_word].text=='Why'
    assert source.words[best.last_word].text=='approach.'


def test_automatic_plan_contract_rejects_out_of_source_or_over_cap_ranges():
    from app.automatic_clips import AutomaticClips
    result=suggest(transcript([' '.join(['word']*50)]),15,'d'*64).model_dump(mode='json')
    result['source_duration_ms']=1
    with pytest.raises(ValidationError):AutomaticClips.model_validate(result)


def test_pauses_find_unpunctuated_passages_without_crossing_long_silence():
    source=transcript([' '.join(['First']*12),' '.join(['Second']*12)],gap=3000)
    plan=suggest(source,30,'d'*64)
    assert plan.candidates
    assert all(not(c.first_word<12<=c.last_word) for c in plan.candidates)


def test_uncertain_word_is_not_a_manual_confirmation_gate_or_falsely_approved():
    source=transcript(['Today we explain a useful lesson that can help people.'])
    words=list(source.words);words[4]=words[4].model_copy(update={'confidence':.2})
    source=source.model_copy(update={'words':tuple(words)})
    plan=suggest(source,15,'d'*64)
    assert plan.candidates and 'uncertain_words' in plan.warnings
    assert plan.transcript_sha256==fingerprint(source)
    assert plan.review_sha256 is None
    assert not suggest(transcript([' '.join(['Uncertain']*15)],confidence=.1),15,'d'*64).candidates


@pytest.mark.parametrize('cap',[5,15,30,60])
def test_all_duration_choices_stay_inside_requested_source_and_frame_caps(cap):
    source=transcript([' '.join(['word']*20)+'.']*10)
    if cap==5:
        words=list(source.words);words[6]=words[6].model_copy(update={'end_ms':5000})
        source=source.model_copy(update={'words':tuple(words)})
    plan=suggest(source,cap,'d'*64)
    assert plan.candidates
    assert all(150<=c.output_frames<=min(1800,cap*30) and
        c.source_end_ms<=source.source_duration_ms for c in plan.candidates)


def test_does_not_pad_or_extend_words_to_force_a_five_second_window():
    source=transcript([' '.join(['word']*20)+'.'])
    assert not suggest(source,5,'d'*64).candidates


def plan_for(client,item):
    return client.get(item['url']+'/automatic-clips',headers=item['owner'])


def queue(client,item,plan,**extra):
    return client.post(item['url']+'/previews',headers=item['owner'],json={
        'revision':plan['revision'],'candidate_number':1,'idempotency_key':str(uuid.uuid4()),
        'acknowledged_preview':True,'automatic_draft':True,**extra})


def test_automatic_options_do_not_create_reviews_or_jobs_and_remain_owner_only(client,prepared):
    imported(prepared)
    with SessionLocal() as db:
        row=db.get(ProjectAnalysis,prepared['jid'])
        before=(row.transcript_json,row.review_json,row.proposal_json,row.revision)
        jobs=list(db.scalars(select(RenderJob.id)))
    response=plan_for(client,prepared)
    assert response.status_code==200 and response.headers['cache-control']=='private, no-store'
    plan=response.json();assert plan['candidates'] and plan['automatic']
    assert plan_for(client,prepared).json()==plan
    assert client.get(prepared['url']+'/automatic-clips',headers=prepared['other']).status_code==404
    assert client.get(prepared['url']+'/automatic-clips').status_code==401
    with SessionLocal() as db:
        row=db.get(ProjectAnalysis,prepared['jid'])
        assert (row.transcript_json,row.review_json,row.proposal_json,row.revision)==before
        assert list(db.scalars(select(RenderJob.id)))==jobs


def test_draft_and_captions_render_without_saved_review_with_explicit_provenance(client,prepared):
    imported(prepared);plan=plan_for(client,prepared).json()
    url=prepared['url']+'/captions'
    response=client.get(url,headers=prepared['owner'],params={
        'revision':plan['revision'],'candidate_number':1,'automatic':True})
    assert response.status_code==200 and response.json()['revision']==plan['revision']
    assert queue(client,prepared,plan,acknowledged_preview=False).status_code==422
    key=str(uuid.uuid4())
    response=queue(client,prepared,plan,idempotency_key=key)
    assert response.status_code==202,response.text
    identity=response.json()['id']
    assert queue(client,prepared,plan,idempotency_key=key).json()['id']==identity
    assert queue(client,prepared,plan,idempotency_key=key,automatic_draft=False).status_code==409
    with SessionLocal() as db:
        spec=ExcerptSpec.model_validate_json(db.get(RenderJob,identity).preview_spec_json)
        assert spec.schema_version=='excerpt-auto-1' and spec.review_sha256 is None
        assert spec.transcript_sha256==fingerprint(prepared['transcript'])
        assert db.get(ProjectAnalysis,prepared['jid']).review_json is None
        bad=spec.model_dump(mode='json');bad['schema_version']='excerpt-1'
        with pytest.raises(ValidationError):ExcerptSpec.model_validate(bad)


def test_changed_review_fences_new_automatic_intents_but_recovers_old_key(client,prepared):
    imported(prepared);plan=plan_for(client,prepared).json();key=str(uuid.uuid4())
    first=queue(client,prepared,plan,idempotency_key=key)
    assert first.status_code==202
    assert client.put(prepared['url']+'/review',headers=prepared['owner'],json=saved_payload(client,prepared)).status_code==200
    reviewed=client.get(prepared['url'],headers=prepared['owner']).json()
    assert plan_for(client,prepared).json()['revision']!=plan['revision']
    assert queue(client,prepared,plan).status_code==409
    assert queue(client,prepared,plan,idempotency_key=key).json()['id']==first.json()['id']
    assert client.get(prepared['url'],headers=prepared['owner']).json()==reviewed


@pytest.mark.parametrize('fence',['cancel','lease','delete'])
def test_automatic_draft_cannot_publish_after_claim_or_source_is_revoked(client,actual,fence):
    from app.worker import claim_job,mark_done,process
    plan=plan_for(client,actual).json()
    response=queue(client,actual,plan);assert response.status_code==202
    identity=response.json()['id'];job=claim_job();assert job['id']==identity
    if fence=='cancel':
        assert client.post('/api/v1/jobs/'+identity+'/cancel',headers=actual['owner']).status_code==200
    elif fence=='delete':
        assert client.delete('/api/v1/jobs/'+actual['jid'],headers=actual['owner']).status_code==202
    else:
        with SessionLocal.begin() as db:db.get(RenderJob,identity).lease_expires_at=utcnow()-timedelta(seconds=1)
    assert not mark_done(identity,job['claim_token'],output_path='forbidden.mp4',output_duration=5)
    process(job)
    with SessionLocal() as db:assert db.get(RenderJob,identity).output_path is None


def test_real_automatic_selected_excerpt_renders_without_sentence_marks(client,actual,tmp_path):
    from app.worker import claim_job,process
    from app.local_transcription import file_digest
    from app.media import probe_video
    with SessionLocal.begin() as db:
        db.delete(db.get(ProjectAnalysis,actual['jid']));db.flush()
        import_transcript(db,owner=actual['uid'],job_id=actual['jid'],transcript=actual['transcript'])
    assert client.get(actual['url'],headers=actual['owner']).json()['review'] is None
    plan=plan_for(client,actual).json()
    candidate=plan['candidates'][0]
    assert candidate['source_start_ms']==1010  # Selected speech, not first-N trim.
    result=queue(client,actual,plan,caption_style='clean-1',polish={})
    assert result.status_code==202,result.text
    job=claim_job();assert job['id']==result.json()['id'];process(job)
    status=client.get('/api/v1/jobs/'+job['id'],headers=actual['owner']).json()
    assert status['status']=='succeeded',status
    download=client.get('/api/v1/jobs/'+job['id']+'/download',headers=actual['owner'])
    assert download.status_code==200
    saved=tmp_path/'automatic.mp4';saved.write_bytes(download.content)
    metadata=probe_video(saved)
    assert metadata['width']==1080 and metadata['height']==1920
    assert metadata['duration']<=candidate['output_frames']/30+.04
    assert file_digest(actual['source'])==actual['transcript'].source_sha256
    assert client.get(actual['url'],headers=actual['owner']).json()['review'] is None
    assert client.delete('/api/v1/jobs/'+actual['jid'],headers=actual['owner']).status_code==202
    assert client.get('/api/v1/jobs/'+job['id']+'/download',headers=actual['owner']).status_code==404
