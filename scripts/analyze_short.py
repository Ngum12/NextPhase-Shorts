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
    from app.analysis_annotations import TranscriptReview, validate_review
    from app.local_transcription import regular_file, file_digest, extract_audio, transcribe
    from app.media import probe_video
    if os.getenv('APP_ENV','development') not in ('development','test'):
        raise RuntimeError('Experimental analysis is not enabled in staging/production')
    if not args.consent_to_local_analysis:
        raise RuntimeError('Explicit local-processing acknowledgement is required')
    replan=getattr(args,'replan_transcript',None)
    annotations=getattr(args,'review_annotations',None)
    review=None
    if annotations and not replan:
        raise RuntimeError('Review annotations require a saved transcript')
    source=None
    if replan:
        if args.transcript or args.engine or args.model or args.engine_sha256 or args.model_sha256:
            raise RuntimeError('Replanning does not accept ASR or manual-import options')
        path=regular_file(replan,maximum=8*1024**2)
        transcript=Transcript.model_validate_json(path.read_bytes())
        if args.language and transcript.language!=args.language:
            raise RuntimeError('Transcript language differs')
        if annotations:
            review_path=regular_file(annotations,maximum=256*1024)
            review=validate_review(transcript,TranscriptReview.model_validate_json(review_path.read_bytes()))
    else:
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
            if replan:
                asr_executed=False
            elif args.transcript:
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
            proposal=propose(transcript,args.requested_seconds,review=review)
            if source is not None and file_digest(source)!=digest:
                raise RuntimeError('Source changed during analysis')
            artifacts={'transcript.json':transcript.model_dump(mode='json'),
                       'proposal.json':proposal.model_dump(mode='json')}
            if review is not None:
                artifacts['review-annotations.json']=review.model_dump(mode='json')
            if proposal.candidates:
                artifacts['proposed-edl.json']=planning_edl(proposal)
            for name,data in artifacts.items():
                with (output/name).open('x',encoding='utf-8') as handle:
                    os.chmod(output/name,0o600)
                    json.dump(data,handle,ensure_ascii=False,indent=2)
            with (output/'review.html').open('x',encoding='utf-8') as handle:
                os.chmod(output/'review.html',0o600)
                handle.write(review_html(transcript,proposal,review=review))
            return {'ok':True,'language':transcript.language,'words':len(transcript.words),
                    'candidate_count':len(proposal.candidates),'asr_executed':asr_executed,
                    'replanned_existing_transcript':bool(replan),
                    'human_annotations_applied':review is not None,
                    'planner_algorithm':proposal.algorithm,'planning_warnings':list(proposal.warnings),
                    'human_review_required':True,'render_enabled':False}
    except BaseException:
        # Output was exclusively created by this invocation. Preserve all inputs.
        shutil.rmtree(output)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    inputs=parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--source')
    inputs.add_argument('--replan-transcript',help='Replan a validated saved transcript; preserve its provenance and run no ASR')
    parser.add_argument('--review-annotations',help='Human sentence boundaries and flagged-word confirmations exported from the review page')
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
    parser.add_argument('--diagnostic',action='store_true',help='Show fixed error classifications; never transcript text or native logs')
    args=parser.parse_args()
    os.umask(0o077)
    try:
        print(json.dumps(analyze(args)))
        return 0
    except Exception as error:
        result={'ok':False,'issue':'analysis_refused_or_failed',
                'inputs_preserved':True,'private_text_printed':False}
        if args.diagnostic:
            from pydantic import ValidationError
            result['error_type']=type(error).__name__
            # Only known fixed messages are mapped; arbitrary exception text is
            # never echoed because validation/native exceptions can contain data.
            reasons={
                'ASR text and token inventory disagree':'token_inventory_mismatch',
                'Invalid ASR vocabulary metadata':'invalid_vocabulary_metadata',
                'Invalid ASR token identity':'invalid_token_identity',
                'Missing or invalid ASR timestamps':'invalid_token_timestamps',
                'ASR token order changed':'token_order_changed',
                'A token spans multiple words; timing is ambiguous':'ambiguous_word_timing',
                'Local transcription failed':'native_transcription_failed',
                'Artifact checksum mismatch':'artifact_checksum_mismatch',
                'Imported transcript is not bound to this source':'source_identity_mismatch',
                'Review is not bound to this transcript':'review_identity_mismatch',
                'Review references missing words':'review_word_out_of_range',
                'Review confirmation requires a flagged word':'review_word_not_flagged',
                'Review annotations require a saved transcript':'review_requires_replan',
                'ASR has not passed the required worker sandbox gate':'sandbox_acceptance_required',
            }
            if isinstance(error,ValidationError):
                result['validation_types']=sorted({item['type'] for item in error.errors(include_input=False,include_url=False)})
            else:
                result['reason_code']='output_exists' if isinstance(error,FileExistsError) else reasons.get(str(error),'unclassified')
        print(json.dumps(result))
        return 1


if __name__=='__main__':raise SystemExit(main())
