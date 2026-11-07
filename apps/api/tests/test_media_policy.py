import copy
import json
import subprocess
from pathlib import Path
import pytest
from app.media import MediaError,probe_video,render_baseline
from app.media_policy import validate_metadata


def metadata():
    return {'format':{'format_name':'mov,mp4,m4a,3gp,3g2,mj2','duration':'5'},
        'streams':[{'codec_type':'video','codec_name':'h264','width':1920,'height':1080,'avg_frame_rate':'30/1'},
                   {'codec_type':'audio','codec_name':'aac','channels':2,'sample_rate':'48000'}]}


@pytest.mark.parametrize('change',[
    lambda d:d['format'].update(format_name='hls'),lambda d:d['format'].update(duration='nan'),
    lambda d:d['format'].update(duration='inf'),lambda d:d['streams'][0].update(width=7680,height=4320),
    lambda d:d['streams'][0].update(codec_name='svg'),lambda d:d['streams'][0].update(avg_frame_rate='240/1'),
    lambda d:d['streams'][0].update(avg_frame_rate='0/0'),
    lambda d:d['streams'][0].update(r_frame_rate='1000/1'),lambda d:d['streams'][0].update(disposition={'attached_pic':1}),
    lambda d:d['streams'][1].update(channels=32),lambda d:d['streams'][1].update(sample_rate='384000'),
    lambda d:d['streams'][1].update(codec_name='unknown'),lambda d:d['streams'].append(d['streams'][0].copy()),
    lambda d:d['streams'].append(d['streams'][1].copy()),lambda d:d.update(streams=d['streams']*5),
])
def test_unsupported_profiles_rejected(change):
    data=metadata();change(data)
    with pytest.raises((ValueError,ZeroDivisionError,TypeError)):validate_metadata(data)


def test_valid_mono_silent_and_variable_frame_rate_metadata():
    data=metadata();data['streams'][1]['channels']=1
    assert validate_metadata(data)['width']==1920
    data['streams'].pop();data['streams'][0].update(avg_frame_rate='0/0',r_frame_rate='30000/1001')
    assert validate_metadata(data)['duration']==5


def test_playlist_with_local_extension_is_rejected_without_network_access(tmp_path,monkeypatch):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from threading import Thread
    requested=[]
    class Canary(BaseHTTPRequestHandler):
        def do_GET(self):
            requested.append(self.path);self.send_response(500);self.end_headers()
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Canary)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    source=tmp_path/'untrusted.mp4'
    source.write_text(f'#EXTM3U\n#EXT-X-TARGETDURATION:5\n#EXTINF:5,\nhttp://127.0.0.1:{server.server_port}/private.ts\n#EXT-X-ENDLIST\n')
    try:
        with pytest.raises(MediaError):probe_video(source)
        # Simulate source replacement after preflight: the renderer itself must
        # still refuse the playlist/network URI, independent of the probe guard.
        monkeypatch.setattr('app.media.probe_video',lambda _: {'duration':5,'width':160,'height':90})
        with pytest.raises(MediaError):render_baseline(source,tmp_path/'rejected.mp4',5)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
    assert requested==[]


@pytest.mark.parametrize('extension,codec,options',[
    ('mp4','libx264',[]),('mov','libx265',['-x265-params','pools=none:frame-threads=1:log-level=error']),
    ('webm','libvpx-vp9',['-deadline','realtime','-cpu-used','8']),
    ('webm','libaom-av1',['-cpu-used','8']),
])
def test_real_supported_containers_and_decoders(tmp_path,extension,codec,options):
    source=tmp_path/('source.'+extension)
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','color=c=navy:s=160x90:r=10',
        '-t','1','-threads','2','-c:v',codec,*options,str(source)],check=True,capture_output=True,timeout=30)
    assert probe_video(source)['duration']>0
    result=render_baseline(source,tmp_path/'out.mp4',1)
    assert result['width']==1080 and result['height']==1920 and result['duration']<=1
