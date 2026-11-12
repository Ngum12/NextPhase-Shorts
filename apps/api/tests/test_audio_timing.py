"""Normalized audio clock and low-energy evidence, not speech-quality proof."""
from array import array
import hashlib
from pathlib import Path
import subprocess
import wave

import pytest
from pydantic import ValidationError
from app.audio_timing import analyze,AudioTiming,QuietInterval
from app.local_transcription import extract_audio
from app.media import MediaCancelled
from app.db import SessionLocal
from app.models import ProjectAnalysis,RenderJob,User
from app.project_analysis import import_transcript,document
from test_project_analysis import prepared
from test_migrations import migration_engine


def pcm(tmp_path,parts,*,rate=16000,channels=1):
    path=tmp_path/'timing.wav'
    with wave.open(str(path),'wb') as wav:
        wav.setparams((channels,2,rate,0,'NONE',''))
        for milliseconds,value in parts:
            wav.writeframes(array('h',[value]*(milliseconds*rate//1000*channels)).tobytes())
    return path


@pytest.mark.parametrize('parts,expected',[
    ([(1000,4000),(600,0),(1000,4000)],[(1000,1600)]),
    ([(500,0),(1000,4000),(500,0)],[(0,500),(1500,2000)]),
    ([(480,0),(1000,4000)],[]),
    ([(2000,0)],[(0,2000)]),
    ([(1000,-32768)],[]),
    ([(1000,327)],[(0,1000)]),
    ([(1000,328)],[]),
])
def test_low_energy_windows_and_minimum_runs_are_bounded(tmp_path,parts,expected):
    source=pcm(tmp_path,parts);before=source.read_bytes();duration=sum(ms for ms,_ in parts)
    timing=analyze(source,source_sha256='a'*64,source_duration_ms=duration)
    assert [(item.start_ms,item.end_ms) for item in timing.quiet_intervals]==expected
    assert timing.audio_duration_ms==duration and timing.method=='pcm_window_energy'
    assert source.read_bytes()==before


def test_cancellation_and_bad_profiles_never_publish_partial_metadata(tmp_path):
    source=pcm(tmp_path,[(1000,0)])
    with pytest.raises(MediaCancelled):analyze(source,source_sha256='a'*64,source_duration_ms=1000,should_cancel=lambda:True)
    with pytest.raises(ValueError):analyze(source,source_sha256='a'*64,source_duration_ms=999)
    with pytest.raises(ValueError):analyze(source,source_sha256='a'*64,source_duration_ms=180001)
    source=pcm(tmp_path,[(1000,0)],channels=2)
    with pytest.raises(ValueError):analyze(source,source_sha256='a'*64,source_duration_ms=1000)
    assert source.exists()


@pytest.mark.parametrize('change',[
    {'quiet_intervals':[{'start_ms':0,'end_ms':499}]},
    {'quiet_intervals':[{'start_ms':0,'end_ms':1000},{'start_ms':500,'end_ms':1500}]},
    {'quiet_intervals':[{'start_ms':1500,'end_ms':2500}]},
    {'audio_duration_ms':2001}, {'threshold_dbfs':-20}, {'window_ms':50},
])
def test_metadata_contract_refuses_ambiguous_or_unbounded_timing(change):
    with pytest.raises(ValidationError):AudioTiming.model_validate(dict(source_sha256='a'*64,
        source_duration_ms=2000,audio_duration_ms=2000,quiet_intervals=())|change)


def test_real_delayed_aac_stays_aligned_with_original_video(tmp_path):
    source=tmp_path/'delayed.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i',
        'testsrc2=size=160x90:rate=15:duration=6','-itsoffset','2','-f','lavfi','-i',
        'sine=frequency=440:sample_rate=16000:duration=4','-map','0:v:0','-map','1:a:0',
        '-t','6','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True,timeout=30)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    output=extract_audio(source,tmp_path/'aligned.wav',duration_ms=6000)
    with wave.open(str(output),'rb') as wav:
        assert wav.getnframes()==96000
        samples=array('h',wav.readframes(16000))
        assert sum(value*value for value in samples)==0
    timing=analyze(output,source_sha256=digest,source_duration_ms=6000)
    assert timing.quiet_intervals[0].start_ms==0
    assert 1960<=timing.quiet_intervals[0].end_ms<=2040
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest


def test_audio_metadata_is_owner_source_bound_and_existing_review_is_preserved(client,prepared):
    timing=AudioTiming(source_sha256=prepared['transcript'].source_sha256,source_duration_ms=12000,
        audio_duration_ms=12000,quiet_intervals=(QuietInterval(start_ms=0,end_ms=1000),))
    with SessionLocal.begin() as db:
        with pytest.raises(ValueError):import_transcript(db,owner=prepared['uid'],job_id=prepared['jid'],
            transcript=prepared['transcript'],audio_timing=timing.model_copy(update={'source_sha256':'0'*64}))
        row=import_transcript(db,owner=prepared['uid'],job_id=prepared['jid'],transcript=prepared['transcript'],audio_timing=timing)
        db.flush();before=document(row);revision=row.revision
        import_transcript(db,owner=prepared['uid'],job_id=prepared['jid'],transcript=prepared['transcript'],
            audio_timing=timing.model_copy(update={'quiet_intervals':()}))
        assert document(row)==before and row.revision==revision
    response=client.get(prepared['url'],headers=prepared['owner'])
    assert response.status_code==200 and response.json()['audio_timing']['quiet_intervals']==[{'start_ms':0,'end_ms':1000}]
    assert client.get(prepared['url'],headers=prepared['other']).status_code==404
    assert client.delete('/api/v1/jobs/'+prepared['jid'],headers=prepared['owner']).status_code==202
    with SessionLocal() as db:assert db.get(ProjectAnalysis,prepared['jid']) is None


def test_migration_retains_legacy_analysis_with_null_optional_timing(migration_engine):
    from alembic import command
    from app.migrate import configuration,upgrade_schema
    from sqlalchemy import text
    with migration_engine.begin() as connection:
        command.upgrade(configuration(connection),'0023_english_analysis')
        connection.execute(User.__table__.insert().values(id='owner',email='fixture@example.invalid',password_hash='fixture'))
        connection.execute(RenderJob.__table__.insert().values(id='source',user_id='owner',title='Fixture',style='vlog',
            desired_seconds=15,source_duration_seconds=5,source_path='fixture',status='cancelled'))
        connection.execute(ProjectAnalysis.__table__.insert().values(job_id='source',transcript_json='fixture-text',
            proposal_json='fixture-plan',review_json='fixture-review',revision='a'*64))
    upgrade_schema(migration_engine)
    with migration_engine.connect() as connection:
        row=connection.execute(text('SELECT transcript_json,review_json,revision,audio_timing_json FROM project_analyses')).one()
        assert tuple(row)==('fixture-text','fixture-review','a'*64,None)


def test_scan_cancellation_after_work_and_truncated_pcm_are_refused(tmp_path):
    source=pcm(tmp_path,[(1000,0)]);calls=iter((False,True))
    with pytest.raises(MediaCancelled):analyze(source,source_sha256='a'*64,source_duration_ms=1000,should_cancel=lambda:next(calls))
    source.write_bytes(source.read_bytes()[:-100])
    with pytest.raises(ValueError):analyze(source,source_sha256='a'*64,source_duration_ms=1000)


def test_existing_analysis_revision_does_not_change_when_optional_timing_is_absent(client,prepared):
    with SessionLocal.begin() as db:
        row=import_transcript(db,owner=prepared['uid'],job_id=prepared['jid'],transcript=prepared['transcript'])
        db.flush();before=row.revision
    data=client.get(prepared['url'],headers=prepared['owner']).json()
    assert data['revision']==before and data['audio_timing'] is None
    assert data['transcript']==prepared['transcript'].model_dump(mode='json')
