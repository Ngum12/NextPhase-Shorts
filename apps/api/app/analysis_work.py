"""Attempt-private analysis scratch; no text/model artifacts survive normal exit."""
import time
from .automatic_analysis import AnalysisSpec,enabled,publish
from .contained_asr import MODEL,transcribe
from .excerpt_jobs import snapshot_source
from .local_transcription import extract_audio
from .media import MediaError,MediaCancelled
from .observability import stage


def process_analysis(job,source,*,should_cancel):
    if not enabled(job['user_id']):raise MediaError('English analysis disabled')
    spec=AnalysisSpec.model_validate_json(job['preview_spec_json'])
    from .config import get_settings
    if spec.model_sha256!=get_settings().english_analysis_model_sha256:raise MediaError('Analysis model changed')
    audio=source.parent/'audio.wav';output=source.parent/'transcript.json'
    began=time.monotonic()
    try:
        with stage('source_fetch'):
            snapshot_source(job,source,should_cancel=should_cancel,spec=spec)
        with stage('audio_extract'):
            extract_audio(source,audio,should_cancel=should_cancel)
        with stage('transcribe'):
            transcript=transcribe(audio,MODEL,source.parent,source_sha256=spec.source_sha256,
                source_duration_ms=spec.source_duration_ms,model_sha256=spec.model_sha256,
                should_cancel=should_cancel,timeout=get_settings().english_analysis_timeout_seconds)
        if should_cancel():raise MediaCancelled('Analysis cancelled')
        with stage('planning'):
            return publish(job,transcript,time.monotonic()-began)
    except (ValueError,RuntimeError) as error:
        if isinstance(error,(MediaError,MediaCancelled)):raise
        raise MediaError('English analysis could not produce a valid transcript') from None
    finally:
        for path in (source,audio,output):path.unlink(missing_ok=True)
