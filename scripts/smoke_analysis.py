"""Reproducible planning demo: synthetic video plus original manual annotations.

This does not benchmark or simulate actual speech recognition quality.
"""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api'))


def main():
    from app.local_transcription import file_digest
    from app.media import probe_video
    from app.analysis_plan import Transcript,Proposal
    output=ROOT/'.data'/('analysis-demo-'+uuid.uuid4().hex)
    output.mkdir(mode=0o700,parents=True)
    source=output/'synthetic.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i',
        'testsrc2=size=320x180:rate=15','-f','lavfi','-i','sine=frequency=440:sample_rate=16000',
        '-t','24','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac',str(source)],
        check=True,timeout=30)
    duration=math.ceil(probe_video(source)['duration']*1000)
    texts={
        'en':('Welcome to this original synthetic timing demonstration. '
              'Here is a complete explanation with enough context to stand on its own. '
              'The result keeps the original words and shows a reviewable proposal. '
              'These annotations were written by a person rather than a speech recognition model.'),
        'fr':('Bienvenue dans cette démonstration synthétique de notre outil. '
              'Voici une explication complète qui conserve le contexte de la discussion originale. '
              'Le résultat garde les mots et présente une proposition à vérifier. '
              'Ces annotations sont écrites par une personne et ne proviennent pas de reconnaissance vocale.')}
    checks={}
    for language,text in texts.items():
        transcript=Transcript(source_sha256=file_digest(source),source_duration_ms=duration,
            language=language,provider='manual',timestamp_quality='operator_supplied',
            words=tuple({'text':word,'start_ms':i*400,'end_ms':i*400+350,
                         'confidence':.95} for i,word in enumerate(text.split())))
        annotations=output/(language+'-manual.json')
        annotations.write_text(transcript.model_dump_json(indent=2),encoding='utf-8')
        response=subprocess.run([sys.executable,str(ROOT/'scripts/analyze_short.py'),
            '--source',str(source),'--transcript',str(annotations),'--output',str(output/language),
            '--requested-seconds','15','--consent-to-local-analysis'],cwd=ROOT,
            text=True,capture_output=True,timeout=30)
        if response.returncode:raise RuntimeError('Manual fixture analysis failed')
        proposal=Proposal.model_validate_json((output/language/'proposal.json').read_bytes())
        if not proposal.candidates:raise RuntimeError('Demo did not produce a proposal')
        if json.loads(response.stdout)['asr_executed']:raise RuntimeError('Fixture mislabeled as ASR')
        checks[language]={'candidates':len(proposal.candidates),
            'output_frames':proposal.candidates[0].output_frames,'human_review_required':True}
    result={'fixture':'synthetic video with original manual annotations',
            'live_asr_tested':False,'checks':checks,'evidence':str(output)}
    (output/'report.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
    return 0


if __name__=='__main__':
    os.umask(0o077)
    raise SystemExit(main())
