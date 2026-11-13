"""Opt-in operator-only local Whisper.cpp adapter. No downloads or cloud ASR.

The operator launcher stays separate from the protected worker launcher in
contained_asr. Token timing/probability are model estimates; real English/French
accuracy requires an independently reviewed set.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import wave

from .analysis_plan import Transcript, Word
from .media import run_render, teardown_decoder
from .media_policy import input_args


class AnalysisUnavailable(RuntimeError):
    pass


class WordTimingUnavailable(AnalysisUnavailable):
    """Invalid model word boundaries, never repaired beyond the bounded policy."""
    pass


def regular_file(path, *, maximum):
    path = Path(path).absolute()
    if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (path, *path.parents)):
        raise AnalysisUnavailable('Use a regular local file')
    if not path.is_file() or not 0 < path.stat().st_size <= maximum:
        raise AnalysisUnavailable('Local file missing or exceeds size limit')
    return path


def file_digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def verified_artifact(path, expected, *, maximum):
    if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise AnalysisUnavailable('A trusted artifact SHA-256 is required')
    path = regular_file(path, maximum=maximum)
    if file_digest(path) != expected:
        raise AnalysisUnavailable('Artifact checksum mismatch')
    return path


def extract_audio(source, destination, *, timeout=120,should_cancel=lambda:False,duration_ms=600000):
    """Bounded file-only decode of one accepted video, mono 16-kHz PCM WAV."""
    if type(duration_ms) is not int or not 1<=duration_ms<=600000:
        raise AnalysisUnavailable('Unsupported analysis audio duration')
    source = regular_file(source, maximum=314572800)
    destination = Path(destination)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    limit = duration_ms*32+4096
    def size_guard():
        if destination.stat().st_size > limit:
            raise AnalysisUnavailable('Analysis audio exceeds bound')
        return should_cancel()
    try:
        run_render(['ffmpeg','-nostdin','-v','error','-y','-max_alloc','67108864',
            *input_args(),'-i',str(source),'-t',f'{duration_ms/1000:.3f}','-map','0:a:0','-vn','-ac','1',
            '-af',f'aresample=16000:async=1:first_pts=0,atrim=end_sample={duration_ms*16}',
            '-ar','16000','-c:a','pcm_s16le','-f','wav',str(destination)],
            timeout,size_guard,max_file_bytes=limit)
        with wave.open(str(destination),'rb') as audio:
            if (audio.getnchannels(),audio.getsampwidth(),audio.getframerate()) != (1,2,16000):
                raise AnalysisUnavailable('Unexpected audio profile')
            if not 0 < audio.getnframes() <= duration_ms*16:
                raise AnalysisUnavailable('Analysis audio duration exceeds bound')
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


def model_word_intervals(words, duration_ms):
    """Repair zero-width model estimates only, with at most two 10-ms ticks.

    Preserve words/scores/order. Positive intervals must already be nonoverlapping;
    unrelated bad timing is not repaired. Small neighboring endpoints may move by
    <=20 ms to leave each recognized word a positive interval inside the source.
    These remain disclosed estimates, never acoustic alignment or verified cuts.
    """
    if not any(word['start_ms']==word['end_ms'] for word in words):
        return words,False
    cursor=0;previous_start=0
    for word in words:
        start,end=word['start_ms'],word['end_ms']
        if start<previous_start or (end>start and start<cursor):
            raise WordTimingUnavailable('ASR word timing is not safely ordered')
        previous_start=start
        if end>start:cursor=end
    repaired=[dict(word) for word in words]
    cursor=0
    for word in repaired:
        word['start_ms']=max(word['start_ms'],cursor)
        word['end_ms']=max(word['end_ms'],word['start_ms']+1)
        cursor=word['end_ms']
    # A zero-width final word at the source boundary borrows only bounded time
    # from its preceding estimate, never from outside the recording.
    cursor=duration_ms
    for word in reversed(repaired):
        word['end_ms']=min(word['end_ms'],cursor)
        word['start_ms']=min(word['start_ms'],word['end_ms']-1)
        cursor=word['start_ms']
    for before,after in zip(words,repaired):
        if (after['start_ms']<0 or after['end_ms']>duration_ms
                or max(abs(before[key]-after[key]) for key in ('start_ms','end_ms'))>20):
            raise WordTimingUnavailable('ASR zero-width timing exceeds repair bound')
    return repaired,True


def parse_whisper(data, *, source_sha256, source_duration_ms, language, model_sha256, engine_sha256):
    if data.get('params',{}).get('translate') is not False or data.get('result',{}).get('language') != language:
        raise AnalysisUnavailable('Unexpected ASR language or translation mode')
    if language == 'fr' and data.get('model',{}).get('multilingual') is not True:
        raise AnalysisUnavailable('French requires a multilingual model')
    model=data.get('model',{})
    multilingual=model.get('multilingual')
    vocab=model.get('vocab')
    if type(multilingual) is not bool or type(vocab) is not int or not 50257<=vocab<=60000:
        raise AnalysisUnavailable('Invalid ASR vocabulary metadata')
    # Pinned whisper.cpp constructs segment text only from IDs below token_eot:
    # 50256 for English-only vocabularies, 50257 for multilingual vocabularies.
    # Its full JSON also includes control tokens such as [_TT_100], which do
    # not have the trailing underscore matched by the old spelling heuristic.
    end_of_text=50257 if multilingual else 50256
    segments = data.get('transcription')
    if not isinstance(segments,list) or len(segments)>5000:
        raise AnalysisUnavailable('Invalid ASR segment inventory')
    words=[]
    tokens_seen=0
    for segment in segments:
        pending=None
        text_pieces=[]
        tokens=segment.get('tokens')
        if not isinstance(tokens,list):
            raise AnalysisUnavailable('Word timestamp data missing')
        for token in tokens:
            tokens_seen+=1
            if tokens_seen>20000:
                raise AnalysisUnavailable('ASR token inventory exceeds bound')
            text=token.get('text')
            if not isinstance(text,str):
                raise AnalysisUnavailable('Invalid ASR token text')
            identity=token.get('id')
            if type(identity) is not int or not 0<=identity<vocab:
                raise AnalysisUnavailable('Invalid ASR token identity')
            if identity>=end_of_text:
                continue
            text_pieces.append(text)
            if not text.strip():
                continue
            offsets=token.get('offsets',{})
            start,end=offsets.get('from'),offsets.get('to')
            if type(start) is not int or type(end) is not int or not 0<=start<=end<=source_duration_ms:
                raise WordTimingUnavailable('Missing or invalid ASR timestamps')
            piece=text.strip()
            if any(c.isspace() for c in piece):
                raise AnalysisUnavailable('A token spans multiple words; timing is ambiguous')
            probability=token.get('p')
            if type(probability) not in (float,int) or not 0<=probability<=1:
                raise AnalysisUnavailable('Invalid ASR token probability')
            starts_word=text[0].isspace() and pending is not None
            if starts_word:
                words.append(pending)
                pending=None
            if pending is None:
                pending={'text':piece,'start_ms':start,'end_ms':end,'confidence':probability}
            else:
                if start < pending['start_ms']:
                    raise AnalysisUnavailable('ASR token order changed')
                pending.update(text=pending['text']+piece,end_ms=max(end,pending['end_ms']),
                               confidence=min(probability,pending['confidence']))
        if pending is not None:
            words.append(pending)
        if ' '.join(''.join(text_pieces).split()) != ' '.join(segment.get('text','').split()):
            raise AnalysisUnavailable('ASR text and token inventory disagree')
    words,adjusted=model_word_intervals(words,source_duration_ms)
    return Transcript(source_sha256=source_sha256,source_duration_ms=source_duration_ms,
        language=language,provider='whisper_cpp',model_sha256=model_sha256,engine_sha256=engine_sha256,
        timestamp_quality='model_token_estimate_adjusted' if adjusted else 'model_token_estimate',
        words=tuple(Word(**word) for word in words))


def transcribe(audio, *, engine, engine_sha256, model, model_sha256,
               language, source_sha256, source_duration_ms, work, timeout=900):
    if not sys.platform.startswith('linux') or os.getenv('APP_ENV','development') not in ('development','test'):
        raise AnalysisUnavailable('Local ASR pilot requires a Linux development environment')
    if os.getenv('WORKER_REQUIRE_SANDBOX','false').lower() == 'true':
        raise AnalysisUnavailable('ASR has not passed the required worker sandbox gate')
    if language not in ('en','fr') or type(timeout) is not int or not 1<=timeout<=1800:
        raise AnalysisUnavailable('Unsupported language or timeout')
    engine=verified_artifact(engine,engine_sha256,maximum=64*1024**2)
    model=verified_artifact(model,model_sha256,maximum=512*1024**2)
    if not os.access(engine,os.X_OK):
        raise AnalysisUnavailable('Local ASR engine is not executable')
    audio=regular_file(audio,maximum=600*16000*2+4096)
    prefix=Path(work)/'whisper-result'
    if prefix.with_suffix('.json').exists():
        raise AnalysisUnavailable('ASR output already exists')
    env={key:value for key,value in os.environ.items() if key.upper() in {'PATH','LANG','LC_ALL','TMPDIR'}}
    env.update(OMP_NUM_THREADS='2',HOME=str(Path(work)),XDG_CACHE_HOME=str(Path(work)))
    args=[str(engine),'-m',str(model),'-f',str(audio),'-l',language,'-t','2','-p','1',
          '-ng','-np','-ojf','-of',str(prefix)]
    cmd=[sys.executable,'-I',str(Path(__file__).with_name('analysis_child.py')),
         str(os.getpid()),str(timeout*2+30),*args]
    output=prefix.with_suffix('.json')
    try:
        with subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,env=env,close_fds=True,start_new_session=True,cwd=work) as child:
            try:
                if child.wait(timeout=timeout):
                    raise AnalysisUnavailable('Local transcription failed')
            finally:
                teardown_decoder(child)
        regular_file(output,maximum=16*1024**2)
        raw=json.loads(output.read_text(encoding='utf-8'))
        if not isinstance(raw,dict):
            raise AnalysisUnavailable('Invalid ASR output')
        return parse_whisper(raw,source_sha256=source_sha256,source_duration_ms=source_duration_ms,
                             language=language,model_sha256=model_sha256,engine_sha256=engine_sha256)
    finally:
        output.unlink(missing_ok=True)
