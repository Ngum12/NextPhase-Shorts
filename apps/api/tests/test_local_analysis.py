"""Real FFmpeg extraction, operator CLI binding and bounded fake-engine protocol.

The executable fixture tests isolation/protocol, not actual speech recognition.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import wave

import pytest

from app.local_transcription import (AnalysisUnavailable, extract_audio, file_digest,
                                     transcribe, verified_artifact)
from app.media import probe_video

ROOT=Path(__file__).resolve().parents[3]


@pytest.fixture
def video(tmp_path):
    path=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i',
        'testsrc2=size=160x90:rate=15','-f','lavfi','-i','sine=frequency=440:sample_rate=16000',
        '-t','8','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac',str(path)],
        check=True,timeout=30)
    return path


def test_real_audio_extraction_is_mono_16k_and_preserves_source(video,tmp_path):
    before=file_digest(video)
    output=extract_audio(video,tmp_path/'analysis.wav')
    with wave.open(str(output),'rb') as audio:
        assert (audio.getnchannels(),audio.getsampwidth(),audio.getframerate())==(1,2,16000)
        assert 0<audio.getnframes()<=9*16000
    assert file_digest(video)==before
    with pytest.raises(FileExistsError):extract_audio(video,output)


def test_artifact_identity_refuses_mismatch_and_links(tmp_path):
    path=tmp_path/'model';path.write_bytes(b'fixture-model')
    assert verified_artifact(path,file_digest(path),maximum=100)==path
    with pytest.raises(AnalysisUnavailable):verified_artifact(path,'0'*64,maximum=100)
    with pytest.raises(AnalysisUnavailable):verified_artifact(path,file_digest(path),maximum=1)
    if os.name=='posix':
        link=tmp_path/'link';link.symlink_to(path)
        with pytest.raises(AnalysisUnavailable):verified_artifact(link,file_digest(path),maximum=100)


@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux operator ASR pilot only')
def test_fake_engine_protocol_and_credential_stripping(tmp_path,monkeypatch):
    engine=tmp_path/'fake-engine'
    data={'params':{'translate':False},'result':{'language':'en'},'model':{'multilingual':True,'vocab':51865},
          'transcription':[{'text':' Hello.', 'tokens':[
              {'text':' Hello','id':2425,'offsets':{'from':0,'to':1000},'p':.9},
              {'text':'.','id':13,'offsets':{'from':1000,'to':1000},'p':.95}]}]}
    engine.write_text(f'#!{sys.executable}\nimport sys,os,json\nfrom pathlib import Path\n'
        'assert all(k not in os.environ for k in ("JWT_SECRET","DATABASE_URL","HTTP_PROXY","ASR_TEST_SECRET"))\n'
        f'Path(sys.argv[sys.argv.index("-of")+1]+".json").write_text({json.dumps(json.dumps(data))})\n')
    engine.chmod(0o700)
    model=tmp_path/'model.bin';model.write_bytes(b'fixture-only-model')
    audio=tmp_path/'audio.wav'
    with wave.open(str(audio),'wb') as handle:
        handle.setparams((1,2,16000,0,'NONE','not compressed'));handle.writeframes(b'\0\0'*32000)
    monkeypatch.setenv('ASR_TEST_SECRET','private-fixture')
    result=transcribe(audio,engine=engine,engine_sha256=file_digest(engine),
        model=model,model_sha256=file_digest(model),language='en',source_sha256='a'*64,
        source_duration_ms=2000,work=tmp_path,timeout=10)
    assert result.words[0].text=='Hello.'
    assert result.provider=='whisper_cpp'  # Fixture protocol, not real ASR evidence.
    assert not (tmp_path/'whisper-result.json').exists()
    monkeypatch.setenv('WORKER_REQUIRE_SANDBOX','true')
    with pytest.raises(AnalysisUnavailable):
        transcribe(audio,engine=engine,engine_sha256=file_digest(engine),model=model,
            model_sha256=file_digest(model),language='en',source_sha256='a'*64,
            source_duration_ms=2000,work=tmp_path)


@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux operator ASR pilot only')
def test_timed_out_engine_is_stopped_and_partial_transcript_removed(tmp_path):
    engine=tmp_path/'slow-engine'
    engine.write_text(f'#!{sys.executable}\nimport os,sys,time\nfrom pathlib import Path\n'
        'Path("asr.pid").write_text(str(os.getpid()))\n'
        'Path(sys.argv[sys.argv.index("-of")+1]+".json").write_text("partial")\n'
        'time.sleep(30)\n')
    engine.chmod(0o700)
    model=tmp_path/'model';model.write_bytes(b'fixture')
    audio=tmp_path/'audio';audio.write_bytes(b'fixture')
    with pytest.raises(subprocess.TimeoutExpired):
        transcribe(audio,engine=engine,engine_sha256=file_digest(engine),model=model,
            model_sha256=file_digest(model),language='en',source_sha256='a'*64,
            source_duration_ms=2000,work=tmp_path,timeout=1)
    assert not (tmp_path/'whisper-result.json').exists()
    with pytest.raises(ProcessLookupError):os.kill(int((tmp_path/'asr.pid').read_text()),0)


@pytest.mark.parametrize('language',['en','fr'])
def test_operator_cli_creates_private_review_for_actual_source(video,tmp_path,language):
    text='This complete sentence describes an original synthetic example.' if language=='en' else \
         'Cette phrase complète décrit un exemple synthétique original.'
    words=[{'text':t,'start_ms':i*800,'end_ms':i*800+650,'confidence':.95} for i,t in enumerate(text.split())]
    value={'source_sha256':file_digest(video),'source_duration_ms':__import__('math').ceil(probe_video(video)['duration']*1000),
        'language':language,'provider':'manual','timestamp_quality':'operator_supplied','words':words}
    source=tmp_path/'manual.json';source.write_text(json.dumps(value),encoding='utf-8')
    output=tmp_path/'review'
    args=[sys.executable,str(ROOT/'scripts/analyze_short.py'),'--source',str(video),
          '--transcript',str(source),'--output',str(output),'--requested-seconds','15','--consent-to-local-analysis']
    response=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert response.returncode==0,response.stdout+response.stderr
    summary=json.loads(response.stdout)
    assert summary['candidate_count'] and not summary['asr_executed']
    assert 'This complete sentence' not in response.stdout
    assert not (output/'analysis').exists()
    assert set(p.name for p in output.iterdir())=={'transcript.json','proposal.json','proposed-edl.json','review.html'}
    assert '<html' in (output/'review.html').read_text()
    if os.name=='posix':
        assert output.stat().st_mode & 0o077==0
        assert all(p.stat().st_mode & 0o077==0 for p in output.iterdir())
    original=(output/'proposal.json').read_bytes()
    again=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert again.returncode!=0
    assert (output/'proposal.json').read_bytes()==original
    value['source_sha256']='0'*64;source.write_text(json.dumps(value))
    args[args.index('--output')+1]=str(tmp_path/'refused')
    refused=subprocess.run(args+['--diagnostic'],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert refused.returncode!=0 and not (tmp_path/'refused').exists()
    assert json.loads(refused.stdout)['reason_code']=='source_identity_mismatch'
    assert text not in refused.stdout
    assert video.exists() and source.exists()


def test_replan_reuses_native_transcript_without_rerunning_asr_or_relabeling_it(tmp_path):
    from app.analysis_plan import Transcript
    original=Transcript(source_sha256='a'*64,source_duration_ms=12000,language='en',
        provider='whisper_cpp',timestamp_quality='model_token_estimate',model_sha256='b'*64,
        engine_sha256='c'*64,words=tuple({'text':'end.' if i%4==3 else 'word',
            'start_ms':i*750,'end_ms':i*750+700,'confidence':.415192 if i==14 else .95}
            for i in range(16)))
    path=tmp_path/'transcript.json';path.write_text(original.model_dump_json())
    before=path.read_bytes()
    output=tmp_path/'replanned'
    response=subprocess.run([sys.executable,str(ROOT/'scripts/analyze_short.py'),
        '--replan-transcript',str(path),'--output',str(output),'--requested-seconds','15',
        '--consent-to-local-analysis'],cwd=ROOT,capture_output=True,text=True,timeout=15)
    assert response.returncode==0,response.stdout+response.stderr
    result=json.loads(response.stdout)
    assert result['replanned_existing_transcript'] and not result['asr_executed']
    assert result['candidate_count']>0 and result['planner_algorithm']=='sentence-window-v2'
    assert result['planning_warnings']==['estimated_timestamps','low_confidence_excluded']
    assert Transcript.model_validate_json((output/'transcript.json').read_bytes())==original
    assert path.read_bytes()==before
