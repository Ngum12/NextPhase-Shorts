"""Phrase layout, data-only text, immutable admission and actual rendered pixels."""
from pathlib import Path
import subprocess
import uuid

import pytest

from app.caption_plan import CaptionCue, captions_for, validate_cues
from app.analysis_plan import Transcript, Candidate
from app.db import SessionLocal
from app.models import RenderJob
from app.excerpt_jobs import ExcerptSpec
from app.excerpt_render import render_excerpt
from app import render_sandbox
from test_excerpt_jobs import actual, prepared, request, review


def test_phrase_wrapping_preserves_words_and_silence():
    words=['These','are','original','words.','Another','complete','sentence.']
    transcript=Transcript(source_sha256='a'*64,source_duration_ms=10000,language='en',
        provider='manual',timestamp_quality='operator_supplied',words=[
            dict(text=text,start_ms=i*1000,end_ms=i*1000+500,confidence=.9)
            for i,text in enumerate(words)])
    candidate=Candidate(first_word=0,last_word=6,source_start_ms=0,source_end_ms=6500,
        output_frames=195,confidence=.9,speech_density=.5,score=.8)
    cues=captions_for(transcript,candidate)
    assert ' '.join(c.text.replace('\n',' ') for c in cues)==' '.join(words)
    assert all(len(line)<=26 for cue in cues for line in cue.text.splitlines())
    assert cues[0].end_ms<cues[1].start_ms  # Half-second silence is not filled.
    with pytest.raises(ValueError):validate_cues([dict(start_ms=0,end_ms=7000,text='Outside')],195)
    with pytest.raises(ValueError):validate_cues([cues[0],cues[0]],195)
    with pytest.raises(ValueError):CaptionCue(start_ms=0,end_ms=500,text='a'*54)


def test_caption_variants_are_source_bound_and_separate_idempotent_requests(client,prepared):
    data=review(client,prepared);key=str(uuid.uuid4())
    plain=request(client,prepared,data,key=key)
    assert plain.status_code==202
    assert request(client,prepared,data,key=key,caption_style='clean-1').status_code==409
    captioned=request(client,prepared,data,caption_style='clean-1')
    assert captioned.status_code==202,captioned.text
    assert captioned.json()['id']!=plain.json()['id']
    with SessionLocal() as db:
        spec=ExcerptSpec.model_validate_json(db.get(RenderJob,captioned.json()['id']).preview_spec_json)
        assert spec.caption_style=='clean-1' and spec.captions
        assert spec.review_revision==data['revision']
    assert request(client,prepared,data,caption_style='arbitrary-filter').status_code==422


def test_actual_caption_queue_renders_private_download_and_cleans_text(client,actual,tmp_path):
    from app.worker import claim_job,process
    response=request(client,actual,actual['data'],caption_style='clean-1')
    assert response.status_code==202,response.text
    process(claim_job())
    jid=response.json()['id']
    with SessionLocal() as db:
        job=db.get(RenderJob,jid)
        assert job.status=='succeeded',job.error_code
        assert not list(Path(job.output_path).parent.glob('caption-*.txt'))
    assert client.get('/api/v1/jobs/'+jid+'/download',headers=actual['owner']).status_code==200


def test_rendered_caption_timing_pixels_and_filter_like_text_remain_data(tmp_path):
    source=tmp_path/'input.mp4';output=tmp_path/'captioned.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i',
        'color=c=black:s=160x90:r=30','-t','7','-c:v','libx264','-threads','2',str(source)],check=True)
    cue=CaptionCue(start_ms=500,end_ms=1500,text="%{n}: 'Hello' [x], \\{}")
    render_excerpt(source,output,start_ms=1010,end_ms=6010,frames=150,
        requested_seconds=15,max_output_bytes=64*1024**2,captions=(cue,))
    def whites(second):
        raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(second),'-i',str(output),
            '-vf','crop=1080:400:0:1400,format=gray','-frames:v','1','-f','rawvideo','pipe:1'])
        return sum(value>200 for value in raw)
    assert whites(.1)<100 and whites(.8)>1000 and whites(2)<100
    assert not list(tmp_path.glob('caption-*.txt'))


def test_caption_sandbox_grants_only_exact_small_attempt_files(tmp_path):
    source=tmp_path/'input.media';source.touch()
    caption=tmp_path/'caption-test.txt';caption.write_text('Original')
    assert render_sandbox.caption_read_paths(source,[caption])==[caption]
    secret=tmp_path/'secret.txt';secret.write_text('no access')
    with pytest.raises(RuntimeError):render_sandbox.caption_read_paths(source,[secret])
    other=tmp_path/'other';other.mkdir();outside=other/'caption-other.txt';outside.touch()
    with pytest.raises(RuntimeError):render_sandbox.caption_read_paths(source,[outside])
    caption.unlink();caption.symlink_to(secret)
    with pytest.raises(RuntimeError):render_sandbox.caption_read_paths(source,[caption])


def test_cancelled_caption_render_removes_private_text_and_partial_output(tmp_path,monkeypatch):
    from app import excerpt_render
    from app.media import MediaCancelled
    source=tmp_path/'input.media';source.touch();output=tmp_path/'output.mp4'
    def cancel(*args,**kwargs):
        assert kwargs['read_files']
        assert all(path.stat().st_mode & 0o777 == 0o600 for path in kwargs['read_files'])
        raise MediaCancelled('Cancelled fixture')
    monkeypatch.setattr(excerpt_render,'run_render',cancel)
    with pytest.raises(MediaCancelled):
        render_excerpt(source,output,start_ms=0,end_ms=5000,frames=150,
            requested_seconds=15,max_output_bytes=1024**2,
            captions=(CaptionCue(start_ms=0,end_ms=1000,text='Original words'),))
    assert not list(tmp_path.glob('caption-*.txt'))
    assert not output.exists() and not output.with_suffix('.partial.mp4').exists()


def test_caption_render_retains_required_sandbox_or_refuses_host(tmp_path,monkeypatch):
    from app.media import MediaError
    source=tmp_path/'input.mp4';output=tmp_path/'output.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i',
        'color=c=black:s=160x90:r=30','-t','5','-c:v','libx264','-threads','2',str(source)],check=True)
    monkeypatch.setenv('WORKER_REQUIRE_SANDBOX','true')
    options=dict(start_ms=0,end_ms=5000,frames=150,requested_seconds=15,
        max_output_bytes=64*1024**2,captions=(CaptionCue(start_ms=0,end_ms=2000,text='Protected caption'),))
    if render_sandbox.supported():
        assert render_excerpt(source,output,**options)['width']==1080
    else:
        with pytest.raises(MediaError):render_excerpt(source,output,**options)
        assert not output.exists()
    assert not list(tmp_path.glob('caption-*.txt'))
