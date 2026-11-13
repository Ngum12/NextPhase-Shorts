"""Manual caption corrections, fixed styles/leveling and complete queued output."""
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import uuid

import pytest

from app.db import SessionLocal
from app.excerpt_jobs import ExcerptSpec
from app.excerpt_render import render_excerpt,output_frames
from app.models import ProjectAnalysis,RenderJob
from app.caption_plan import CaptionCue
from app.polish import PolishSettings,clip_audio_filter
from test_excerpt_jobs import actual,prepared,review


def draft(client,item,data,**kwargs):
    return client.get(item['url']+'/captions',headers=item['owner'],
        params={'revision':data['revision'],'candidate_number':1,**kwargs})


def request(client,item,data,**changes):
    body=dict(revision=data['revision'],candidate_number=1,idempotency_key=str(uuid.uuid4()),
        acknowledged_preview=True,caption_style='clean-1',polish={})
    body.update(changes)
    return client.post(item['url']+'/previews',headers=item['owner'],json=body)


def test_caption_draft_is_owner_revision_bound_private_and_not_a_transcript_rewrite(client,prepared):
    data=review(client,prepared)
    response=draft(client,prepared,data)
    assert response.status_code==200,response.text
    assert response.headers['Cache-Control']=='private, no-store'
    result=response.json()
    assert result['job_id']==prepared['jid'] and result['cues'] and result['duration_ms']<=15000
    assert draft(client,prepared,data,revision='0'*64).status_code==409
    assert draft(client,prepared,data,candidate_number=0).status_code==422
    assert draft(client,{**prepared,'owner':prepared['other']},data).status_code==404
    assert draft(client,{**prepared,'owner':{}},data).status_code==401


def test_edited_caption_snapshot_is_acknowledged_immutable_and_idempotent(client,prepared):
    data=review(client,prepared);cues=draft(client,prepared,data).json()['cues']
    cues[0]['text']='Corrected original words'
    cues[0]['end_ms']-=50
    with SessionLocal() as db:original=db.get(ProjectAnalysis,prepared['jid']).transcript_json
    key=str(uuid.uuid4())
    body=dict(caption_edits=cues,acknowledged_caption_edits=True,idempotency_key=key,
              polish=dict(caption_size='large',caption_color='yellow',caption_position='middle',voice='level'))
    first=request(client,prepared,data,**body)
    assert first.status_code==202,first.text
    assert request(client,prepared,data,**body).json()['id']==first.json()['id']
    changed={**body,'polish':{**body['polish'],'voice':'original'}}
    assert request(client,prepared,data,**changed).status_code==409
    with SessionLocal() as db:
        job=db.get(RenderJob,first.json()['id']);spec=ExcerptSpec.model_validate_json(job.preview_spec_json)
        assert spec.caption_edits_applied and spec.captions[0].text==cues[0]['text']
        assert spec.polish.voice=='level' and spec.polish.caption_color=='yellow'
        assert db.get(ProjectAnalysis,prepared['jid']).transcript_json==original
        assert spec.review_revision==data['revision'] and 'polished' in job.title
    assert request(client,prepared,data,caption_edits=cues).status_code==422
    overlapping=[dict(cue) for cue in cues]
    if len(overlapping)>1:overlapping[1]['start_ms']=overlapping[0]['start_ms']
    else:overlapping[0]['end_ms']=60000
    assert request(client,prepared,data,caption_edits=overlapping,acknowledged_caption_edits=True).status_code==422


@pytest.mark.parametrize('change',[
    {'polish':{'caption_color':'drawtext=evil'}},
    {'polish':{'voice':'movie=https://example.invalid'}},
    {'polish':{'audio_edges':'amovie=https://example.invalid'}},
    {'polish':{'fontfile':'/etc/passwd'}},
    {'caption_edits':[{'text':'word','start_ms':0,'end_ms':60000}],'acknowledged_caption_edits':True},
    {'caption_edits':[],'acknowledged_caption_edits':True},
])
def test_invalid_edits_and_appearance_are_refused_before_queue(client,prepared,change):
    data=review(client,prepared)
    assert request(client,prepared,data,**change).status_code==422


def test_actual_polished_child_renders_and_downloads_with_original_source_preserved(client,actual):
    from app.worker import claim_job,process
    data=actual['data'];cues=draft(client,actual,data).json()['cues']
    cues[0]['text']='Original corrected words'
    response=request(client,actual,data,framing='fill-center',caption_edits=cues,
        acknowledged_caption_edits=True,polish=dict(caption_size='large',caption_color='yellow',caption_position='middle',voice='level'))
    assert response.status_code==202,response.text
    before=hashlib.sha256(actual['source'].read_bytes()).hexdigest()
    process(claim_job());jid=response.json()['id']
    with SessionLocal() as db:
        job=db.get(RenderJob,jid)
        assert job.status=='succeeded',job.error_code
        assert output_frames(Path(job.output_path))==150
        assert not list(Path(job.output_path).parent.glob('caption-*.txt'))
    assert client.get('/api/v1/jobs/'+jid+'/download',headers=actual['owner']).status_code==200
    assert client.get('/api/v1/jobs/'+jid+'/download',headers={}).status_code==401
    assert hashlib.sha256(actual['source'].read_bytes()).hexdigest()==before
    assert client.delete('/api/v1/jobs/'+jid,headers=actual['owner']).status_code==202
    with SessionLocal() as db:assert db.get(RenderJob,jid).preview_spec_json is None


def samples(path):
    pcm=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-ss','2','-t','1',
        '-vn','-ar','16000','-ac','1','-f','s16le','pipe:1'])
    return struct.unpack('<'+'h'*(len(pcm)//2),pcm)


def test_rendered_style_pixels_and_leveling_change_volume_without_changing_pitch(tmp_path):
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=160x90:r=30',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=16000','-af','volume=0.05','-t','6',
        '-c:v','libx264','-threads','2','-c:a','aac',str(source)],check=True)
    original=tmp_path/'original.mp4';leveled=tmp_path/'leveled.mp4'
    for path,settings in ((original,PolishSettings()),(leveled,PolishSettings(
            caption_size='large',caption_color='yellow',caption_position='middle',voice='level'))):
        render_excerpt(source,path,start_ms=0,end_ms=5000,frames=150,requested_seconds=15,
            max_output_bytes=64*1024**2,captions=(CaptionCue(start_ms=0,end_ms=5000,text='Original words.'),),polish=settings)
    quiet=samples(original);loud=samples(leveled)
    rms=lambda values:math.sqrt(sum(v*v for v in values)/len(values))
    assert rms(loud)>rms(quiet)*1.5
    assert max(abs(v) for v in loud)<32760
    crossings=sum((a<=0<b) for a,b in zip(loud,loud[1:]))
    assert 435<=crossings<=445
    frame=subprocess.check_output(['ffmpeg','-v','error','-ss','1','-i',str(leveled),
        '-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','pipe:1'])
    yellow=sum(frame[i]>150 and frame[i+1]>130 and frame[i+2]<150
        for y in range(1100,1300) for x in range(150,930) for i in [(y*1080+x)*3])
    assert yellow>2000
    assert output_frames(leveled)==150


def test_soft_audio_edges_are_bounded_and_source_clocked(tmp_path):
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=160x90:r=30',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','8',
        '-c:v','libx264','-threads','2','-c:a','aac',str(source)],check=True)
    raw=tmp_path/'raw.mp4';soft=tmp_path/'soft.mp4'
    for output,polish in ((raw,PolishSettings()),(soft,PolishSettings(audio_edges='soft'))):
        render_excerpt(source,output,start_ms=2000,end_ms=7000,frames=150,
            requested_seconds=15,max_output_bytes=64*1024**2,polish=polish)
    def rms_at(path,at,seconds=.03):
        audio=subprocess.check_output(['ffmpeg','-v','error','-ss',str(at),'-i',str(path),
            '-t',str(seconds),'-vn','-ar','48000','-ac','1','-f','s16le','pipe:1'])
        samples=struct.unpack('<'+'h'*(len(audio)//2),audio)
        return math.sqrt(sum(value*value for value in samples)/len(samples))
    assert output_frames(soft)==output_frames(raw)==150
    assert rms_at(soft,0.01)<rms_at(raw,0.01)*.45
    assert rms_at(soft,2)>rms_at(raw,2)*.8
    assert rms_at(soft,4.96)<rms_at(raw,4.96)*.45
    assert 'afade=t=in:st=2.000000:d=0.08' in clip_audio_filter(
        PolishSettings(audio_edges='soft'),start_ms=2000,frames=150)
    assert 'afade=t=out:st=6.920000:d=0.08' in clip_audio_filter(
        PolishSettings(audio_edges='soft'),start_ms=2000,frames=150)
    assert clip_audio_filter(PolishSettings(),start_ms=2000,frames=150) is None


def test_leveling_allows_source_without_audio(tmp_path):
    source=tmp_path/'silent.mp4';output=tmp_path/'result.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=160x90:r=30',
        '-t','5','-c:v','libx264','-threads','2',str(source)],check=True)
    info=render_excerpt(source,output,start_ms=0,end_ms=5000,frames=150,requested_seconds=15,
        max_output_bytes=64*1024**2,polish=PolishSettings(voice='level'))
    assert info['duration']==pytest.approx(5,abs=.034)
