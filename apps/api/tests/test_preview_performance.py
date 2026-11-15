"""Original source clock with cheap preroll and high-frame-rate sampling."""
import subprocess
from pathlib import Path

import pytest

from app.caption_plan import CaptionCue
from app.excerpt_render import render_excerpt,output_frames
from app.media import RenderDeadlineExceeded
from test_excerpt_jobs import actual,prepared


def test_filter_order_avoids_scaling_unused_frames_without_changing_absolute_clock(tmp_path,monkeypatch):
    commands=[]
    def capture(command,timeout,*args,**kwargs):
        commands.append(command)
        raise subprocess.TimeoutExpired(command,timeout)
    monkeypatch.setattr('app.excerpt_render.run_render',capture)
    source=tmp_path/'source.mp4';source.touch();out=tmp_path/'output.mp4'
    with pytest.raises(RenderDeadlineExceeded):
        render_excerpt(source,out,start_ms=45010,end_ms=74510,frames=885,
            requested_seconds=30,max_output_bytes=64*1024**2,framing='fill-center',
            captions=(CaptionCue(start_ms=100,end_ms=1000,text='Synthetic caption.'),))
    command=commands[0];vf=command[command.index('-vf')+1]
    assert vf.startswith('fps=30,trim=start=44.933333333,crop=')
    assert vf.count('fps=30')==1 and vf.index('trim=')<vf.index('scale=')<vf.index('drawtext=')
    assert 'gte(t,45.110)' in vf and 'lt(t,46.010)' in vf
    assert command[command.index('-ss')+1]=='45.010'
    assert not out.exists() and not list(tmp_path.glob('*.partial.mp4'))
    assert not list(tmp_path.glob('caption-*.txt'))


def test_worker_publishes_fixed_deadline_code_and_cleans_artifacts(client,actual,monkeypatch,caplog):
    from app.worker import claim_job,process
    from test_automatic_clips import queue,plan_for
    plan=plan_for(client,actual).json()
    result=queue(client,actual,plan,caption_style='clean-1');assert result.status_code==202
    def timed_out(command,timeout,*args,**kwargs):
        assert timeout<=300
        raise subprocess.TimeoutExpired(['private-source-text'],timeout)
    monkeypatch.setattr('app.excerpt_render.run_render',timed_out)
    job=claim_job();assert job['id']==result.json()['id'];process(job)
    status=client.get('/api/v1/jobs/'+job['id'],headers=actual['owner']).json()
    assert status['status']=='failed' and status['error_code']=='RENDER_DEADLINE_EXCEEDED'
    assert 'private-source-text' not in caplog.text


def test_hfr_885_frame_crop_with_19_captions_matches_legacy_pixels_and_frame_count(tmp_path,monkeypatch):
    import hashlib,json,time
    from app.excerpt_render import run_render as native_render
    from app.preview_framing import framing_filter
    source=tmp_path/'hfr.mp4';output=tmp_path/'optimized.mp4';legacy=tmp_path/'legacy.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc2=s=320x180:r=60',
        '-f','lavfi','-i','sine=frequency=880:sample_rate=48000','-t','38',
        '-c:v','libx264','-preset','ultrafast','-threads','2','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True,timeout=60)
    before=hashlib.sha256(source.read_bytes()).hexdigest();timings={}
    def compare(command,timeout,guard,**kwargs):
        prior=list(command);index=prior.index('-vf')+1
        captions=prior[index].split(',drawtext=',1)[1]
        prior[index]=framing_filter('fill-center')+',drawtext='+captions
        prior[-1]=str(legacy)
        began=time.monotonic();native_render(prior,timeout,guard,**kwargs);timings['legacy_seconds']=time.monotonic()-began
        began=time.monotonic();result=native_render(command,timeout,guard,**kwargs);timings['optimized_seconds']=time.monotonic()-began
        return result
    monkeypatch.setattr('app.excerpt_render.run_render',compare)
    cues=tuple(CaptionCue(start_ms=i*1500,end_ms=i*1500+1000,text=f'Synthetic caption {i}.') for i in range(19))
    render_excerpt(source,output,start_ms=8010,end_ms=37510,frames=885,requested_seconds=30,
        max_output_bytes=64*1024**2,framing='fill-center',captions=cues)
    assert output_frames(output)==output_frames(legacy)==885
    for second in (0.2,15.2,28.2):
        def pixels(path):
            return subprocess.check_output(['ffmpeg','-v','error','-ss',str(second),'-i',str(path),
                '-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','pipe:1'],timeout=30)
        assert pixels(output)==pixels(legacy)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    assert not list(tmp_path.glob('caption-*.txt'))
    # Evidence only: timing assertions would be flaky on shared CI hosts.
    (tmp_path/'benchmark.json').write_text(json.dumps(timings))
