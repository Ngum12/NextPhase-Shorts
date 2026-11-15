"""Real private synthetic scenes, source voice, frame QA and closed storyboard."""
import hashlib,json,struct,subprocess,math
from datetime import datetime,timezone
from pathlib import Path
import pytest
from pydantic import ValidationError
from app.documentary_plan import AssetReceipt,DocumentaryPlan,DocumentaryFailure
from app.documentary_render import render_documentary,checksum
from app.excerpt_render import output_frames
from app.media import probe_video,MediaCancelled
from app.render_sandbox import composition_read_paths


def fixture_source(tmp_path):
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=0x102639:s=320x180:r=30',
        '-f','lavfi','-i','sine=frequency=880:sample_rate=48000','-t','6','-c:v','libx264','-threads','2','-c:a','aac',str(source)],check=True,timeout=30)
    return source


def receipt(path,kind):
    return AssetReceipt(asset_id=checksum(path),kind=kind,origin='original',creator='Original test author',title='Synthetic fixture',
        license='CC0-1.0',retrieved_at=datetime.now(timezone.utc).isoformat(),bytes=path.stat().st_size,original_rights_confirmed=True)


def plan(source,asset,kind='image'):
    return DocumentaryPlan(source_sha256=checksum(source),source_start_ms=0,source_end_ms=5000,output_frames=150,requested_seconds=5,
        scenes=({'kind':'source','start_frame':0,'end_frame':60,'heading':'A CLEAR BEGINNING'},
        {'kind':kind,'start_frame':60,'end_frame':150,'asset_id':asset.asset_id,'motion':'push_in' if kind=='image' else 'hold',
            'heading':'SHOW THE EVIDENCE','kicker':'Original voice continues'}))


@pytest.mark.parametrize('kind',['image','video'])
def test_scene_composition_produces_full_portrait_short_with_original_voice(tmp_path,kind):
    source=fixture_source(tmp_path);before=checksum(source)
    visual=tmp_path/('asset.jpg' if kind=='image' else 'asset.webm')
    command=['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc2=s=320x180:r=30']
    if kind=='image':command+=['-frames:v','1','-c:v','mjpeg','-threads','1',str(visual)]
    else:command+=['-f','lavfi','-i','sine=frequency=220:sample_rate=48000','-t','4','-c:v','libvpx','-threads','2','-c:a','libvorbis',str(visual)]
    subprocess.run(command,check=True,timeout=30);asset=receipt(visual,kind);output=tmp_path/'documentary.mp4'
    result=render_documentary(source,output,plan(source,asset,kind),{asset.asset_id:(asset,visual)})
    info=probe_video(output)
    assert result['scene_count']==2 and result['frames']==150 and output_frames(output)==150
    assert (info['width'],info['height'])==(1080,1920) and info['duration']<=5
    assert checksum(source)==before and not list(tmp_path.glob('documentary-*'))
    pcm=subprocess.check_output(['ffmpeg','-v','error','-ss','3','-i',str(output),'-t','0.1','-vn','-ac','1','-ar','48000','-f','s16le','pipe:1'])
    samples=struct.unpack('<'+'h'*(len(pcm)//2),pcm)
    def power(hz):return sum(v*math.sin(2*math.pi*hz*i/48000) for i,v in enumerate(samples))**2+sum(v*math.cos(2*math.pi*hz*i/48000) for i,v in enumerate(samples))**2
    assert power(880)>100*power(220)  # External video audio must never replace the original voice.


def test_editorial_card_is_rendered_as_original_motion_graphics(tmp_path):
    source=fixture_source(tmp_path);output=tmp_path/'card.mp4'
    value=DocumentaryPlan(source_sha256=checksum(source),source_start_ms=0,source_end_ms=5000,output_frames=150,requested_seconds=5,
        scenes=({'kind':'card','start_frame':0,'end_frame':60,'heading':'THE BIG IDEA','kicker':'A documentary proof'},
                {'kind':'source','start_frame':60,'end_frame':150}))
    render_documentary(source,output,value,{})
    assert output_frames(output)==150


@pytest.mark.parametrize('mutation',['gap','overlap','overrun','missing_asset','code','reverse'])
def test_storyboard_rejects_uncovered_frames_unknown_assets_and_executable_motion(mutation):
    value=dict(source_sha256='a'*64,source_start_ms=0,source_end_ms=5000,output_frames=150,requested_seconds=5,
        scenes=[dict(kind='source',start_frame=0,end_frame=60),dict(kind='card',start_frame=60,end_frame=150)])
    if mutation=='gap':value['scenes'][1]['start_frame']=61
    if mutation=='overlap':value['scenes'][1]['start_frame']=59
    if mutation=='overrun':value['source_end_ms']=5001
    if mutation=='missing_asset':value['scenes'][1]['kind']='image'
    if mutation=='code':value['scenes'][1]['motion']='eval(shell)'
    if mutation=='reverse':value['scenes'][1]['end_frame']=30
    with pytest.raises(ValidationError):DocumentaryPlan.model_validate(value)


def test_cancelled_documentary_never_publishes_and_removes_attempt_files(tmp_path):
    source=fixture_source(tmp_path);output=tmp_path/'cancelled.mp4'
    value=DocumentaryPlan(source_sha256=checksum(source),source_start_ms=0,source_end_ms=5000,output_frames=150,requested_seconds=5,
        scenes=({'kind':'card','start_frame':0,'end_frame':60},{'kind':'source','start_frame':60,'end_frame':150}))
    with pytest.raises(MediaCancelled):render_documentary(source,output,value,{},should_cancel=lambda:True)
    assert not output.exists() and not list(tmp_path.glob('documentary-*'))


def test_composition_grants_exact_scene_files_and_refuses_links_or_other_directories(tmp_path):
    listing=tmp_path/'scene-list.ffconcat';listing.write_text('ffconcat version 1.0\nfile scene-00.mp4\n')
    allowed=tmp_path/'scene-00.mp4';allowed.write_bytes(b'fixture')
    assert composition_read_paths(listing,[allowed])==[allowed.resolve()]
    secret=tmp_path/'secret.env';secret.write_text('not granted')
    with pytest.raises(RuntimeError):composition_read_paths(listing,[secret])
    link=tmp_path/'scene-01.mp4';link.symlink_to(allowed)
    with pytest.raises(RuntimeError):composition_read_paths(listing,[link])
