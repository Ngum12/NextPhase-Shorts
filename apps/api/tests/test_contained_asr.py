"""Native protocol fixture and cancellation, not speech-recognition evidence."""
import json
import os
from pathlib import Path
import sys
import pytest
from app.contained_asr import transcribe
from app.local_transcription import file_digest
from app.media import MediaError,MediaCancelled

@pytest.fixture
def inference(tmp_path):
    data={'params':{'translate':False},'result':{'language':'en'},'model':{'multilingual':True,'vocab':51865},
        'transcription':[{'text':' Hello.', 'tokens':[
            {'text':' Hello','id':2425,'offsets':{'from':0,'to':1000},'p':.9},
            {'text':'.','id':13,'offsets':{'from':1000,'to':1000},'p':.95}]}]}
    engine=tmp_path/'engine'
    engine.write_text(f'#!{sys.executable}\nimport sys,os\nfrom pathlib import Path\n'
        'assert all(k not in os.environ for k in ("JWT_SECRET","DATABASE_URL","HTTP_PROXY","ASR_TEST_SECRET"))\n'
        f'Path(sys.argv[sys.argv.index("-of")+1]+".json").write_text({json.dumps(json.dumps(data))})\n')
    engine.chmod(0o700)
    model=tmp_path/'model';model.write_bytes(b'fixture-model')
    audio=tmp_path/'audio.wav';audio.write_bytes(b'fixture-audio')
    return dict(audio=audio,model=model,work=tmp_path,engine=engine,engine_digest=file_digest(engine),
        model_sha256=file_digest(model),source_sha256='a'*64,source_duration_ms=2000,timeout=5,should_cancel=lambda:False)

def test_protocol_strips_credentials_and_removes_intermediate(inference,monkeypatch):
    monkeypatch.setenv('ASR_TEST_SECRET','not-real-secret')
    transcript=transcribe(**inference)
    assert transcript.language=='en' and transcript.words[0].text=='Hello.'
    assert not (inference['work']/'transcript.json').exists()

def test_required_mode_fails_closed_on_untrusted_fixture_paths(inference,monkeypatch):
    monkeypatch.setenv('WORKER_REQUIRE_SANDBOX','true')
    with pytest.raises(MediaError):transcribe(**inference)
    assert not (inference['work']/'transcript.json').exists()

@pytest.mark.parametrize('cancel',[False,True])
def test_bounded_timeout_and_cancellation_kill_child(inference,cancel):
    engine=inference['engine'];engine.write_text(f'#!{sys.executable}\nimport os,time\nfrom pathlib import Path\nPath("asr.pid").write_text(str(os.getpid()))\ntime.sleep(30)\n')
    inference['engine_digest']=file_digest(engine);inference['timeout']=.8
    inference['should_cancel']=lambda:cancel and (inference['work']/'asr.pid').exists()
    with pytest.raises(MediaCancelled if cancel else MediaError):transcribe(**inference)
    assert not (inference['work']/'transcript.json').exists()
    with pytest.raises(ProcessLookupError):os.kill(int((inference['work']/'asr.pid').read_text()),0)

def test_wrong_artifact_never_executes(inference):
    inference['model_sha256']='0'*64
    with pytest.raises(RuntimeError):transcribe(**inference)
    assert not (inference['work']/'transcript.json').exists()

def test_model_bootstrap_pins_model_and_preserves_existing_configuration(tmp_path,monkeypatch):
    import importlib.util
    root=Path(__file__).resolve().parents[3]
    spec=importlib.util.spec_from_file_location('model_bootstrap',root/'scripts/prepare_english_analysis.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    trial=tmp_path/'.data/vps-trial';trial.mkdir(parents=True)
    env=trial/'server.env';env.write_text('ENGLISH_REVIEW_ENABLED=true\nJWT_SECRET=private-fixture\n');env.chmod(0o600)
    source=tmp_path/'.data/asr-pilot/ggml-base.bin';source.parent.mkdir();source.write_bytes(b'fixture-model')
    import hashlib
    with pytest.raises(RuntimeError):module.prepare(tmp_path,True)
    assert 'ENGLISH_ANALYSIS_ENABLED' not in env.read_text()
    monkeypatch.setattr(module,'BASE_SHA1',hashlib.sha1(source.read_bytes()).hexdigest())
    assert module.prepare(tmp_path,True)['enabled']
    target=trial/'asr/ggml-base.bin';assert target.stat().st_mode&0o777==0o444
    assert 'JWT_SECRET=private-fixture' in env.read_text() and env.stat().st_mode&0o777==0o600
    assert module.prepare(tmp_path,True)['model_sha256']==file_digest(source)
    target.chmod(0o600);target.write_bytes(b'wrong model')
    with pytest.raises(RuntimeError):module.prepare(tmp_path,True)


def _engine_result(inference, result):
    """Synthetic protocol only; never a transcription quality test."""
    engine=inference['engine']
    if result is None:
        engine.write_text(f'#!{sys.executable}\nimport sys\nsys.exit(17)\n')
    else:
        payload=json.dumps(result)
        engine.write_text(f'#!{sys.executable}\nimport sys\nfrom pathlib import Path\n'
            f'Path(sys.argv[sys.argv.index("-of")+1]+".json").write_text({payload!r})\n')
    engine.chmod(0o700)
    inference['engine_digest']=file_digest(engine)


@pytest.mark.parametrize('mode,code',[
    ('exit','ASR_PROCESS_FAILED'),
    ('malformed','ASR_OUTPUT_INVALID'),
    ('protocol','ASR_TRANSCRIPT_REJECTED'),
    ('timing','ASR_WORD_TIMING_REJECTED'),
])
def test_private_whisper_failure_category_is_closed_and_non_content(inference,mode,code):
    from app.asr_failures import AsrFailure
    data={'params':{'translate':False},'result':{'language':'en'},
          'model':{'multilingual':True,'vocab':51865},
          'transcription':[{'text':' Private text.', 'tokens':[
              {'text':' Private','id':2425,'offsets':{'from':0,'to':400},'p':.9},
              {'text':' text','id':1510,'offsets':{'from':400,'to':1000},'p':.9},
              {'text':'.','id':13,'offsets':{'from':1000,'to':1000},'p':.95}]}]}
    if mode=='exit':_engine_result(inference,None)
    elif mode=='malformed':
        # A true JSON syntax error, not a Whisper language/protocol error.
        engine=inference['engine']
        engine.write_text(f'#!{sys.executable}\nimport sys\nfrom pathlib import Path\n'
            'Path(sys.argv[sys.argv.index("-of")+1]+".json").write_text("{bad")\n')
        inference['engine_digest']=file_digest(engine)
    else:
        if mode=='protocol':data['result']['language']='fr'
        else:data['transcription'][0]['tokens'][0]['offsets']['to']=2001
        _engine_result(inference,data)
    with pytest.raises(AsrFailure) as failed:transcribe(**inference)
    assert failed.value.code==code
    assert 'Private' not in str(failed.value)
    assert not (inference['work']/'transcript.json').exists()


def test_diagnostic_codes_reject_arbitrary_exception_data():
    from app.asr_failures import AsrFailure
    with pytest.raises(ValueError):
        AsrFailure('Private transcript: hello')
