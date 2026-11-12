"""Transparent diversity ranking over immutable validated source intervals."""
import pytest
from app.analysis_plan import Candidate,Transcript,Word,propose
from app.analysis_annotations import TranscriptReview,fingerprint
from app.clip_selection import diverse,overlap,ALGORITHM


def candidate(start,end,score):
    return Candidate(first_word=0,last_word=1,source_start_ms=start,source_end_ms=end,
        output_frames=(end-start)*30//1000,confidence=.9,speech_density=.9,score=score)


def test_near_duplicate_suppression_and_other_regions_get_a_chance():
    first=candidate(0,30000,.99);duplicate=candidate(1000,30000,.98)
    later=candidate(40000,65000,.90);shorter=candidate(0,15000,.95)
    source=[first,duplicate,later,shorter]
    result=diverse(source)
    assert result==[first,later,shorter]
    assert duplicate not in result
    assert all(overlap(a,b)<.85 for i,a in enumerate(result) for b in result[i+1:])
    assert all(item in source for item in result) and source[0].score==.99


def test_same_score_ties_are_deterministic_and_output_is_bounded():
    source=[candidate(i*6000,i*6000+5000,.8) for i in range(10)]
    assert diverse(source)==diverse(reversed(source))==source[:5]
    assert diverse([])==[]


def reviewed():
    transcript=Transcript(source_sha256='a'*64,source_duration_ms=60000,language='en',
        provider='manual',timestamp_quality='operator_supplied',words=tuple(
            Word(text='sentence.' if i%4==3 else 'word',start_ms=i*1500,end_ms=(i+1)*1500,confidence=.9)
            for i in range(40)))
    review=TranscriptReview(source_sha256=transcript.source_sha256,transcript_sha256=fingerprint(transcript),
        acknowledged_original_recording=True,sentence_end_words=tuple(range(4,41,4)),confirmed_low_confidence_words=())
    return transcript,review


def test_diversity_keeps_reviewed_complete_source_windows_and_fallback():
    transcript,review=reviewed()
    result=propose(transcript,15,review=review)
    assert result.algorithm==ALGORITHM and result.human_review_required and not result.semantic_quality_verified
    assert 1<=len(result.candidates)<=5 and result==propose(transcript,15,review=review)
    for item in result.candidates:
        assert (item.last_word+1) in review.sentence_end_words
        assert item.first_word==0 or item.first_word in review.sentence_end_words
        assert item.source_start_ms==transcript.words[item.first_word].start_ms
        assert item.source_end_ms==transcript.words[item.last_word].end_ms
        assert item.output_frames<=450
    assert propose(transcript,15).algorithm=='sentence-window-v2'


def test_exact_plan_is_bound_into_new_revisions_but_legacy_hashes_remain():
    from app.project_analysis import revision_for
    transcript,review=reviewed();plan=propose(transcript,15,review=review)
    legacy=plan.model_copy(update={'algorithm':'sentence-window-v3-reviewed'})
    old=revision_for(transcript,review)
    assert revision_for(transcript,review,legacy)==old
    new=revision_for(transcript,review,plan)
    assert new!=old
    changed=plan.model_copy(update={'candidates':tuple(reversed(plan.candidates))})
    assert revision_for(transcript,review,changed)!=new


def test_real_worker_renders_the_selected_alternative_exactly(client,monkeypatch,tmp_path):
    from test_excerpt_jobs import actual,request
    from app.db import SessionLocal
    from app.models import ProjectAnalysis,RenderJob
    from app.project_analysis import import_transcript
    from app.worker import claim_job,process
    from app.media import probe_video
    from pathlib import Path
    item=actual.__wrapped__(client,monkeypatch,tmp_path)
    transcript=item['transcript'].model_copy(update={'words':tuple(
        Word(text='end.' if i%4==3 else 'word',start_ms=i*250,end_ms=(i+1)*250,confidence=.9)
        for i in range(24))})
    with SessionLocal.begin() as db:
        db.delete(db.get(ProjectAnalysis,item['jid']));db.flush()
        import_transcript(db,owner=item['uid'],job_id=item['jid'],transcript=transcript)
    review=TranscriptReview(source_sha256=transcript.source_sha256,transcript_sha256=fingerprint(transcript),
        acknowledged_original_recording=True,sentence_end_words=(4,8,12,16,20,24),confirmed_low_confidence_words=())
    current=client.get(item['url'],headers=item['owner']).json()
    saved=client.put(item['url']+'/review',headers=item['owner'],json=dict(revision=current['revision'],review=review.model_dump(mode='json')))
    assert saved.status_code==200,saved.text
    plan=saved.json();assert len(plan['proposal']['candidates'])==2
    selected=plan['proposal']['candidates'][1]
    assert selected['source_start_ms']==1000 and selected['source_end_ms']==6000
    queued=request(client,item,plan,number=2);assert queued.status_code==202,queued.text
    job=claim_job();assert job['id']==queued.json()['id'];process(job)
    with SessionLocal() as db:
        child=db.get(RenderJob,job['id']);assert child.status=='succeeded'
        assert child.output_duration_seconds==pytest.approx(5,abs=.034)
        assert probe_video(Path(child.output_path))['duration']<=5.034
