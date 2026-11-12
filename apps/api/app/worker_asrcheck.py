"""Verify immutable worker inference artifacts without customer media or text."""
import json
import os
from .config import get_settings
from .contained_asr import ENGINE,ENGINE_DIGEST,MODEL
from .local_transcription import verified_artifact


def check():
    settings=get_settings()
    if not settings.english_analysis_enabled:return {'ready':True,'enabled':False}
    if os.getenv('WORKER_REQUIRE_SANDBOX','false').lower()!='true':raise RuntimeError('Protected analysis worker required')
    from .render_sandbox import require_support
    require_support()
    verified_artifact(ENGINE,ENGINE_DIGEST.read_text().strip(),maximum=64*1024**2)
    verified_artifact(MODEL,settings.english_analysis_model_sha256,maximum=160*1024**2)
    if MODEL.stat().st_mode & 0o222 or ENGINE.stat().st_mode & 0o022:raise RuntimeError('Read-only artifacts required')
    return {'ready':True,'enabled':True,'inference_tested':False}


if __name__=='__main__':
    try:print(json.dumps(check()))
    except Exception:print(json.dumps({'ready':False,'issue':'analysis_artifacts_or_isolation_unavailable'}));raise SystemExit(1)
