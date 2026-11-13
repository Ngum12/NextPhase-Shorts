"""Worker-only English inference; bounded files, cancellation and native isolation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .local_transcription import verified_artifact,parse_whisper,regular_file,WordTimingUnavailable
from .asr_failures import AsrFailure
from .media import MediaCancelled,MediaError,teardown_decoder
from .resource_measure import DecoderSamples
from .observability import active_attributes

ENGINE=Path('/opt/nextphase-asr/whisper-cli')
ENGINE_DIGEST=Path('/opt/nextphase-asr/engine.sha256')
MODEL=Path('/opt/nextphase-asr-model/ggml-base.bin')
OUTPUT_CAP=16*1024**2


def transcribe(audio,model,work,*,source_sha256,source_duration_ms,model_sha256,should_cancel,timeout=900,
               engine=ENGINE,engine_digest=None):
    if not sys.platform.startswith('linux'):raise MediaError('Analysis requires Linux')
    engine_digest=engine_digest or ENGINE_DIGEST.read_text().strip()
    engine=verified_artifact(engine,engine_digest,maximum=64*1024**2)
    verified_artifact(model,model_sha256,maximum=160*1024**2)
    audio=regular_file(audio,maximum=600*16000*2+4096)
    output=Path(work)/'transcript.json'
    with output.open('xb'):os.chmod(output,0o600)
    required=os.getenv('WORKER_REQUIRE_SANDBOX','false').lower()=='true'
    if not required and os.getenv('APP_ENV','development') not in ('development','test'):
        raise MediaError('Native test mode is unavailable')
    policy={'required':required,'audio':str(audio),'model':str(Path(model).absolute()),'output':str(output.absolute())}
    args=[str(engine),'-m',str(model),'-f',str(audio),'-l','en','-t','2','-p','1','-ng','-np','-ojf','-of',str(output.with_suffix(''))]
    cmd=[sys.executable,'-I',str(Path(__file__).with_name('contained_asr_child.py')),str(os.getpid()),str(int(timeout*2+30)),json.dumps(policy),*args]
    env={key:value for key,value in os.environ.items() if key.upper() in ('PATH','LANG','LC_ALL')}
    env.update(PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='2',HOME=str(work),XDG_CACHE_HOME=str(work))
    measured=DecoderSamples();began=time.monotonic()
    try:
        with subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                              env=env,close_fds=True,start_new_session=True,cwd=work) as child:
            try:
                while child.poll() is None:
                    measured.sample(child.pid)
                    if should_cancel():raise MediaCancelled('Analysis cancelled')
                    if time.monotonic()-began>=timeout:raise AsrFailure('ASR_DEADLINE_EXCEEDED')
                    try:child.wait(timeout=.25)
                    except subprocess.TimeoutExpired:pass
                if child.returncode:raise AsrFailure('ASR_PROCESS_FAILED')
            finally:teardown_decoder(child)
        if should_cancel():raise MediaCancelled('Analysis cancelled')
        try:
            raw=json.loads(regular_file(output,maximum=OUTPUT_CAP).read_bytes())
        except (OSError,ValueError,UnicodeError,RuntimeError):
            # Never return raw Whisper JSON, text, path or parser error.
            raise AsrFailure('ASR_OUTPUT_INVALID') from None
        if not isinstance(raw,dict):raise AsrFailure('ASR_OUTPUT_INVALID')
        try:
            return parse_whisper(raw,source_sha256=source_sha256,source_duration_ms=source_duration_ms,
                language='en',model_sha256=model_sha256,engine_sha256=engine_digest)
        except WordTimingUnavailable:
            raise AsrFailure('ASR_WORD_TIMING_REJECTED') from None
        except (ValueError,RuntimeError,TypeError,KeyError):
            raise AsrFailure('ASR_TRANSCRIPT_REJECTED') from None
    finally:
        output.unlink(missing_ok=True)
        if active_attributes.get() is not None:active_attributes.get().update(measured.attributes())
