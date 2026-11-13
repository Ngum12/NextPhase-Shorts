"""Sampled visual changes and optional bounded proxy, not semantic scene proof."""
import hashlib
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError
from app.scene_analysis import (analyze,read_proxy,SceneAnalysis,SceneUnavailable,unavailable,
                                FRAME_BYTES,MAX_PROXY_BYTES,ADDRESS_BYTES)
from app.media import MediaCancelled,decoder_invocation
from app.db import SessionLocal
from app.models import ProjectAnalysis,RenderJob,User
from app.project_analysis import import_transcript,document
from test_project_analysis import prepared
from test_migrations import migration_engine


def meta(**changes):
    return dict(source_sha256='a'*64,source_duration_ms=6000,status='available',issue=None,
        sample_count=12,analyzed_duration_ms=6000,changes=())|changes


@pytest.fixture
def source(tmp_path):
    path=tmp_path/'cut.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i',
        'color=black:size=160x90:rate=15:duration=3','-f','lavfi','-i',
        'color=white:size=160x90:rate=15:duration=3','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0',
        '-c:v','libx264','-threads','2','-pix_fmt','yuv420p',str(path)],check=True,timeout=30)
    return path


def test_real_hard_cut_is_sampled_without_changing_source_or_retaining_pixels(source):
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    timing=analyze(source,source_sha256=digest,source_duration_ms=6000)
    assert timing.status=='available' and timing.sample_count==12 and timing.analyzed_duration_ms==6000
    assert len(timing.changes)==1 and timing.changes[0].at_ms==3000 and timing.changes[0].delta_milli>=180
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    assert list(source.parent.iterdir())==[source]


def test_flat_proxy_and_strongest_nearby_change_are_deterministic(tmp_path):
    path=tmp_path/'proxy.rgb'
    path.write_bytes(bytes([20])*FRAME_BYTES*8)
    assert not read_proxy(path,source_sha256='a'*64,source_duration_ms=4000,should_cancel=lambda:False).changes
    path.write_bytes(b''.join(bytes([level])*FRAME_BYTES for level in (0,60,255,255)))
    result=read_proxy(path,source_sha256='a'*64,source_duration_ms=2000,should_cancel=lambda:False)
    assert [(change.at_ms,change.delta_milli) for change in result.changes]==[(1000,764)]


@pytest.mark.parametrize('change',[
    {'changes':[{'at_ms':0,'delta_milli':900}]},
    {'changes':[{'at_ms':6000,'delta_milli':900}]},
    {'changes':[{'at_ms':1250,'delta_milli':900}]},
    {'changes':[{'at_ms':1000,'delta_milli':900},{'at_ms':1500,'delta_milli':900}]},
    {'changes':[{'at_ms':1000,'delta_milli':179}]},
    {'sample_count':13,'analyzed_duration_ms':6500},
    {'sample_count':14}, {'proxy_width':640}, {'sample_interval_ms':10},
    {'status':'unavailable','issue':'decode_or_resource_limit'},
])
def test_metadata_refuses_impossible_or_unbounded_visual_claims(change):
    with pytest.raises(ValidationError):SceneAnalysis.model_validate(meta(**change))


def test_unavailable_does_not_claim_missing_analysis_as_zero_changes():
    result=unavailable(source_sha256='a'*64,source_duration_ms=6000)
    assert result.status=='unavailable' and result.issue=='decode_or_resource_limit'
    assert not result.sample_count and not result.analyzed_duration_ms and not result.changes


def test_decode_timeout_is_optional_but_cancellation_is_preserved(source,monkeypatch):
    def timeout(*a,**kw):
        assert kw['max_file_bytes']==MAX_PROXY_BYTES and kw['address_limit_bytes']==ADDRESS_BYTES
        raise subprocess.TimeoutExpired('synthetic decoder',60)
    monkeypatch.setattr('app.scene_analysis.run_render',timeout)
    with pytest.raises(SceneUnavailable):analyze(source,source_sha256='a'*64,source_duration_ms=6000)
    assert list(source.parent.iterdir())==[source]
    def cancelled(*a,**kw):raise MediaCancelled('fixture cancellation')
    monkeypatch.setattr('app.scene_analysis.run_render',cancelled)
    with pytest.raises(MediaCancelled):analyze(source,source_sha256='a'*64,source_duration_ms=6000)
    assert list(source.parent.iterdir())==[source]


@pytest.mark.parametrize('decode_seconds,prefix_frames,cancel_at',[(75,0,None),(125,4,None),(125,2,None),(125,0,None),(125,4,70)])
def test_slow_decoder_can_finish_or_keep_truthful_partial_coverage(source,monkeypatch,decode_seconds,prefix_frames,cancel_at):
    # Exercise the real subprocess watchdog with a deterministic clock/process,
    # rather than sleeping for minutes or requiring a particular CPU speed.
    import os
    from app import media
    clock=[0.0]
    class Decoder:
        pid=os.getpid()
        returncode=None
        def __init__(self,command,**kwargs):
            self.output=Path(command[-1])
            if prefix_frames:self.output.write_bytes(bytes(FRAME_BYTES*prefix_frames)+b'unfinished')
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def wait(self,timeout):
            clock[0]+=timeout
            if clock[0]<decode_seconds:raise subprocess.TimeoutExpired('fixture',timeout)
            self.output.write_bytes(bytes(FRAME_BYTES*12))
            self.returncode=0
    class Samples:
        def sample(self,*args):pass
        def attributes(self):return {}
    monkeypatch.setattr(media.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(media.subprocess,'Popen',Decoder)
    monkeypatch.setattr(media,'DecoderSamples',Samples)
    monkeypatch.setattr(media,'teardown_decoder',lambda process:None)
    def run():
        return analyze(source,source_sha256='a'*64,source_duration_ms=6000,
            should_cancel=lambda:cancel_at is not None and clock[0]>=cancel_at)
    if cancel_at is not None:
        with pytest.raises(MediaCancelled):run()
        assert clock[0]==cancel_at
    elif decode_seconds<120 or prefix_frames>=3:
        result=run()
        count=12 if decode_seconds<120 else prefix_frames-1
        assert result.status=='available' and result.sample_count==count
        assert result.analyzed_duration_ms==count*500
    else:
        with pytest.raises(SceneUnavailable):run()
        assert clock[0]==120
    assert list(source.parent.iterdir())==[source]


def test_bad_proxy_shape_and_short_sources_cannot_claim_available_analysis(tmp_path,source):
    path=tmp_path/'proxy.rgb';path.write_bytes(b'partial')
    with pytest.raises(ValueError):read_proxy(path,source_sha256='a'*64,source_duration_ms=6000,should_cancel=lambda:False)
    path.write_bytes(bytes(FRAME_BYTES))
    with pytest.raises(SceneUnavailable):read_proxy(path,source_sha256='a'*64,source_duration_ms=6000,should_cancel=lambda:False)
    with pytest.raises(SceneUnavailable):analyze(source,source_sha256='a'*64,source_duration_ms=400)


def test_scene_metadata_is_source_bound_private_and_deleted_with_parent(client,prepared):
    timing=SceneAnalysis.model_validate(meta(source_sha256=prepared['transcript'].source_sha256,source_duration_ms=12000,
        sample_count=24,analyzed_duration_ms=12000,changes=[{'at_ms':3000,'delta_milli':900}]))
    with SessionLocal.begin() as db:
        with pytest.raises(ValueError):import_transcript(db,owner=prepared['uid'],job_id=prepared['jid'],
            transcript=prepared['transcript'],scene_analysis=timing.model_copy(update={'source_sha256':'0'*64}))
        row=import_transcript(db,owner=prepared['uid'],job_id=prepared['jid'],transcript=prepared['transcript'],scene_analysis=timing)
        db.flush();before=document(row)
        import_transcript(db,owner=prepared['uid'],job_id=prepared['jid'],transcript=prepared['transcript'],
            scene_analysis=unavailable(source_sha256=timing.source_sha256,source_duration_ms=12000))
        assert document(row)==before
    response=client.get(prepared['url'],headers=prepared['owner'])
    assert response.status_code==200 and response.headers['cache-control']=='private, no-store'
    assert response.json()['scene_analysis']['changes']==[{'at_ms':3000,'delta_milli':900}]
    assert client.get(prepared['url'],headers=prepared['other']).status_code==404
    assert client.delete('/api/v1/jobs/'+prepared['jid'],headers=prepared['owner']).status_code==202
    with SessionLocal() as db:assert db.get(ProjectAnalysis,prepared['jid']) is None


def test_migration_preserves_legacy_analysis_and_audio_metadata(migration_engine):
    from alembic import command
    from app.migrate import configuration,upgrade_schema
    from sqlalchemy import text
    with migration_engine.begin() as connection:
        command.upgrade(configuration(connection),'0024_audio_timing')
        connection.execute(User.__table__.insert().values(id='owner',email='fixture@example.invalid',password_hash='fixture'))
        connection.execute(RenderJob.__table__.insert().values(id='source',user_id='owner',title='Keep',style='vlog',
            desired_seconds=15,source_duration_seconds=5,source_path='fixture',status='cancelled'))
        connection.execute(ProjectAnalysis.__table__.insert().values(job_id='source',transcript_json='keep-text',
            proposal_json='keep-plan',review_json='keep-review',audio_timing_json='keep-audio',revision='a'*64))
    upgrade_schema(migration_engine)
    with migration_engine.connect() as connection:
        row=connection.execute(text('SELECT transcript_json,audio_timing_json,revision,scene_analysis_json FROM project_analyses')).one()
        assert tuple(row)==('keep-text','keep-audio','a'*64,None)


@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux kernel resource guard')
def test_scene_decoder_address_and_file_bounds_are_kernel_enforced(tmp_path,monkeypatch):
    monkeypatch.setenv('WORKER_REQUIRE_SANDBOX','false')
    cmd,env,_=decoder_invocation(['ffmpeg','-version'],10,max_file_bytes=MAX_PROXY_BYTES,address_limit_bytes=ADDRESS_BYTES)
    assert cmd[cmd.index('--address-limit')+1]==str(ADDRESS_BYTES)
    assert cmd[cmd.index('--file-limit')+1]==str(MAX_PROXY_BYTES)
    source=tmp_path/'source.mp4';source.write_bytes(b'fixture')
    output=tmp_path/'output.rgb';output.touch()
    monkeypatch.setenv('WORKER_REQUIRE_SANDBOX','true')
    guarded,_,_=decoder_invocation(['ffmpeg','-i',str(source),str(output)],10,max_file_bytes=MAX_PROXY_BYTES,address_limit_bytes=ADDRESS_BYTES)
    assert guarded.index('--file-limit')<guarded.index('--address-limit')<guarded.index('--sandbox')
    helper=Path(__file__).resolve().parents[1]/'app/render_child.py'
    script=(f'import importlib.util,sys,os,resource,mmap\n'
        f'spec=importlib.util.spec_from_file_location("child",{str(helper)!r});m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\n'
        f'sys.argv=[str(m.__file__),str(os.getppid()),"10","--file-limit","{MAX_PROXY_BYTES}","--address-limit","{ADDRESS_BYTES}","ffmpeg"]\n'
        'def verify(*args):\n'
        f' assert resource.getrlimit(resource.RLIMIT_AS)==({ADDRESS_BYTES},{ADDRESS_BYTES})\n'
        f' assert resource.getrlimit(resource.RLIMIT_FSIZE)==({MAX_PROXY_BYTES},{MAX_PROXY_BYTES})\n'
        ' try: mmap.mmap(-1,2*1024**3)\n'
        ' except (OSError,MemoryError): print("allocation blocked");return\n'
        ' raise AssertionError("allocation escaped bound")\n'
        'm.os.execvp=verify;m.main()\n')
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,env=env,timeout=15)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='allocation blocked'
