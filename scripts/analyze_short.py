"""Operator-only local transcript/planning pilot, separate from the running app."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api'))


def analyze(args):
    from app.analysis_plan import Transcript, propose, planning_edl
    from app.analysis_review import review_html
    from app.local_transcription import regular_file, file_digest, extract_audio, transcribe
    from app.media import probe_video
    if os.getenv('APP_ENV','development') not in ('development','test'):
        raise RuntimeError('Experimental analysis is not enabled in staging/production')
    if not args.consent_to_local_analysis:
        raise RuntimeError('Explicit local-processing acknowledgement is required')
    source=regular_file(args.source,maximum=314572800)
    metadata=probe_video(source)
    if metadata['duration']>600:
        raise RuntimeError('Source exceeds 10-minute analysis limit')
    duration=math.ceil(metadata['duration']*1000)
    digest=file_digest(source)
    output=Path(args.output).absolute()
    if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (output,*output.parents)):
        raise RuntimeError('Use a new private output directory')
    output.mkdir(mode=0o700)
    try:
        with tempfile.TemporaryDirectory(prefix='analysis-',dir=output) as work:
            if args.transcript:
                path=regular_file(args.transcript,maximum=2*1024**2)
                transcript=Transcript.model_validate_json(path.read_bytes())
                if transcript.provider!='manual':
                    raise RuntimeError('Imported transcripts must disclose manual provenance')
                if transcript.source_sha256!=digest or transcript.source_duration_ms!=duration:
                    raise RuntimeError('Imported transcript is not bound to this source')
                if args.language and transcript.language!=args.language:
                    raise RuntimeError('Imported transcript language differs')
                asr_executed=False
            else:
                if not all((args.engine,args.engine_sha256,args.model,args.model_sha256,args.language)):
                    raise RuntimeError('Select manual input or complete local ASR configuration')
                audio=extract_audio(source,Path(work)/'audio.wav')
                transcript=transcribe(audio,engine=args.engine,engine_sha256=args.engine_sha256,
                    model=args.model,model_sha256=args.model_sha256,language=args.language,
                    source_sha256=digest,source_duration_ms=duration,work=work,timeout=args.timeout)
                asr_executed=True
            proposal=propose(transcript,args.requested_seconds)
            if file_digest(source)!=digest:
                raise RuntimeError('Source changed during analysis')
            artifacts={'transcript.json':transcript.model_dump(mode='json'),
                       'proposal.json':proposal.model_dump(mode='json')}
            if proposal.candidates:
                artifacts['proposed-edl.json']=planning_edl(proposal)
            for name,data in artifacts.items():
                with (output/name).open('x',encoding='utf-8') as handle:
                    os.chmod(output/name,0o600)
                    json.dump(data,handle,ensure_ascii=False,indent=2)
            with (output/'review.html').open('x',encoding='utf-8') as handle:
                os.chmod(output/'review.html',0o600)
                handle.write(review_html(transcript,proposal))
            return {'ok':True,'language':transcript.language,'words':len(transcript.words),
                    'candidate_count':len(proposal.candidates),'asr_executed':asr_executed,
                    'human_review_required':True,'render_enabled':False}
    except BaseException:
        # Output was exclusively created by this invocation. Preserve all inputs.
        shutil.rmtree(output)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--requested-seconds',type=int,choices=range(5,61),default=15)
    parser.add_argument('--consent-to-local-analysis',action='store_true')
    parser.add_argument('--transcript',help='Manual timestamped transcript JSON bound to this file')
    parser.add_argument('--language',choices=('en','fr'))
    parser.add_argument('--engine',help='Trusted local whisper-cli path; never a client-supplied path')
    parser.add_argument('--engine-sha256')
    parser.add_argument('--model',help='Trusted local GGML model; no automatic download')
    parser.add_argument('--model-sha256')
    parser.add_argument('--timeout',type=int,default=900)
    args=parser.parse_args()
    os.umask(0o077)
    try:
        print(json.dumps(analyze(args)))
        return 0
    except Exception:
        print(json.dumps({'ok':False,'issue':'analysis_refused_or_failed',
                          'inputs_preserved':True,'private_text_printed':False}))
        return 1


if __name__=='__main__':raise SystemExit(main())
