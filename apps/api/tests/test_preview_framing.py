"""Real pixel/frame/audio checks and immutable framing choice admission."""
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import uuid

import pytest

from app.caption_plan import CaptionCue
from app.db import SessionLocal
from app.excerpt_jobs import ExcerptSpec
from app.excerpt_render import output_frames, render_excerpt
from app.media import MediaError, probe_video
from app.models import RenderJob
from app.preview_framing import framing_filter
from test_excerpt_jobs import actual, prepared, request, review


def frame(path, second=.5):
    return subprocess.check_output(['ffmpeg','-v','error','-ss',str(second),'-i',str(path),
        '-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','pipe:1'])


def pixel(raw,x,y):
    offset=(y*1080+x)*3
    return tuple(raw[offset:offset+3])


@pytest.fixture
def bands(tmp_path):
    source=tmp_path/'landscape.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i',
        'color=c=lime:s=320x180:r=30','-f','lavfi','-i',
        r'aevalsrc=sin(2*PI*if(lt(t\,1)\,440\,880)*t):s=16000',
        '-vf','drawbox=x=0:y=0:w=80:h=180:c=red:t=fill,drawbox=x=240:y=0:w=80:h=180:c=blue:t=fill',
        '-t','7','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac',str(source)],
        check=True,timeout=30)
    return source


def render(source,dest,**kwargs):
    return render_excerpt(source,dest,start_ms=1010,end_ms=6010,frames=150,
        requested_seconds=15,max_output_bytes=64*1024**2,**kwargs)


def test_real_fit_and_center_crop_have_expected_pixels_and_unchanged_audio(bands,tmp_path):
    before=hashlib.sha256(bands.read_bytes()).hexdigest()
    fit=tmp_path/'fit.mp4';fill=tmp_path/'fill.mp4'
    render(bands,fit)
    info=render(bands,fill,framing='fill-center')
    assert info['duration']==pytest.approx(5,abs=.034)
    assert output_frames(fill)==150 and info['width']==1080 and info['height']==1920
    fitted=frame(fit);cropped=frame(fill)
    assert max(pixel(fitted,100,100))<10  # Bars in fit mode.
    assert pixel(fitted,100,960)[0]>180 and pixel(fitted,980,960)[2]>180
    for x,y in ((100,100),(980,100),(100,1800),(980,1800)):
        r,g,b=pixel(cropped,x,y)
        assert g>180 and r<50 and b<50  # Native center only, filled to every edge.
    assert hashlib.sha256(bands.read_bytes()).hexdigest()==before
    # The selected interval begins after the 440 -> 880 Hz source change.
    pcm=subprocess.check_output(['ffmpeg','-v','error','-i',str(fill),'-t','0.1','-vn',
        '-ar','16000','-ac','1','-f','s16le','pipe:1'])
    samples=struct.unpack('<'+'h'*(len(pcm)//2),pcm)
    def power(hz):
        return sum(s*math.sin(2*math.pi*hz*i/16000) for i,s in enumerate(samples))**2 + \
               sum(s*math.cos(2*math.pi*hz*i/16000) for i,s in enumerate(samples))**2
    assert power(880)>10*power(440)


def test_manual_left_and_right_focus_reframes_wide_source_without_touching_original(bands,tmp_path):
    source_hash=hashlib.sha256(bands.read_bytes()).hexdigest()
    for position,channel,other in (('fill-left',0,2),('fill-right',2,0)):
        output=tmp_path/(position+'.mp4')
        info=render(bands,output,framing=position)
        assert info['width']==1080 and info['height']==1920
        assert info['duration']==pytest.approx(5,abs=.034)
        assert output_frames(output)==150
        values=pixel(frame(output),540,960)
        assert values[channel]>150 and values[other]<100
    assert hashlib.sha256(bands.read_bytes()).hexdigest()==source_hash


@pytest.mark.parametrize('size,sar',[('160x640','1/1'),('320x180','2/1'),('1920x16','1/1')])
def test_tall_anamorphic_and_very_wide_sources_stay_bounded_and_square_pixel(tmp_path,size,sar):
    source=tmp_path/'source.mp4';output=tmp_path/'output.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c=lime:s={size}:r=30',
        '-vf',f'setsar={sar}','-t','7','-c:v','libx264','-threads','2',str(source)],check=True,timeout=30)
    render(source,output,framing='fill-center')
    assert output_frames(output)==150 and probe_video(output)['height']==1920
    stream=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
        '-show_entries','stream=sample_aspect_ratio','-of','json',str(output)]))['streams'][0]
    assert stream['sample_aspect_ratio']=='1:1'


def test_crop_and_captions_compose_without_moving_the_caption_safe_area(bands,tmp_path):
    output=tmp_path/'captioned-crop.mp4'
    render(bands,output,framing='fill-center',captions=(
        CaptionCue(start_ms=200,end_ms=1800,text='Original words.'),))
    raw=frame(output)
    assert sum(raw[(y*1080+x)*3]>220 and raw[(y*1080+x)*3+2]>220
        for y in range(1500,1600) for x in range(200,880))>1000
    assert pixel(raw,100,100)[1]>180
    assert not list(tmp_path.glob('caption-*.txt'))


def test_framing_admission_is_closed_and_retries_preserve_legacy_fit_hashes(client,prepared):
    data=review(client,prepared);key=str(uuid.uuid4())
    plain=request(client,prepared,data,key=key)
    assert plain.status_code==202
    assert request(client,prepared,data,key=key,framing='fill-center').status_code==409
    crop_key=str(uuid.uuid4())
    crop=request(client,prepared,data,key=crop_key,framing='fill-center')
    assert crop.status_code==202,crop.text
    assert request(client,prepared,data,key=crop_key,framing='fill-center').json()['id']==crop.json()['id']
    assert request(client,prepared,data,framing='crop=anything').status_code==422
    with SessionLocal() as db:
        original=db.get(RenderJob,plain.json()['id'])
        expected=f"{prepared['jid']}:{data['revision']}:1"
        assert original.request_hash==hashlib.sha256(expected.encode()).hexdigest()
        legacy=json.loads(original.preview_spec_json);legacy.pop('framing')
        assert ExcerptSpec.model_validate(legacy).framing=='fit'
        child=db.get(RenderJob,crop.json()['id'])
        assert ExcerptSpec.model_validate_json(child.preview_spec_json).framing=='fill-center'
        assert child.preview_parent_id==prepared['jid'] and 'crop' in child.title
    assert request(client,{**prepared,'owner':prepared['other']},data,framing='fill-center').status_code==404


@pytest.mark.parametrize('focus', ['fill-left', 'fill-right'])
def test_manual_anchor_requests_are_owner_bound_and_idempotent(client,prepared,focus):
    data=review(client,prepared)
    key=str(uuid.uuid4())
    result=request(client,prepared,data,key=key,framing=focus)
    assert result.status_code==202,result.text
    assert request(client,prepared,data,key=key,framing=focus).json()['id']==result.json()['id']
    assert request(client,prepared,data,key=key,framing='fill-center').status_code==409
    with SessionLocal() as db:
        child=db.get(RenderJob,result.json()['id'])
        assert ExcerptSpec.model_validate_json(child.preview_spec_json).framing==focus
    assert request(client,{**prepared,'owner':prepared['other']},data,framing=focus).status_code==404


def test_actual_cropped_captioned_job_uses_existing_worker_and_private_download(client,actual):
    from app.worker import claim_job,process
    response=request(client,actual,actual['data'],framing='fill-center',caption_style='clean-1')
    assert response.status_code==202,response.text
    process(claim_job())
    jid=response.json()['id']
    with SessionLocal() as db:
        job=db.get(RenderJob,jid)
        assert job.status=='succeeded',job.error_code
        assert output_frames(Path(job.output_path))==150
        assert not list(Path(job.output_path).parent.glob('caption-*.txt'))
    assert client.get('/api/v1/jobs/'+jid+'/download',headers=actual['owner']).status_code==200
    assert client.get('/api/v1/jobs/'+actual['jid'],headers=actual['owner']).status_code==200


def test_arbitrary_framing_refused_before_output_creation(tmp_path):
    with pytest.raises(MediaError,match='framing'):
        render(tmp_path/'source.mp4',tmp_path/'output.mp4',framing='movie=https://example.invalid')
    assert list(tmp_path.iterdir())==[]
    for anchor in ('fill-center','fill-left','fill-right'):
        assert framing_filter(anchor).index('crop=')<framing_filter(anchor).index('scale=')
    assert 'x=0:' in framing_filter('fill-left')
    assert 'x=iw-ow:' in framing_filter('fill-right')
    assert 'x=(iw-ow)/2:' in framing_filter('fill-center')
