"""Generate a synthetic fit/fill comparison; no ASR, real footage or face tracking."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api'))

from app.caption_plan import CaptionCue
from app.excerpt_render import CAPTION_FONT, output_frames, render_excerpt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.data/portrait-framing-demo')
    args=parser.parse_args()
    os.umask(0o077)
    folder=args.output.absolute()
    folder.mkdir(parents=True)  # A new folder only; preserve existing evidence.
    source=folder/'synthetic-source.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i',
        'color=c=0x244654:s=960x540:r=30','-f','lavfi','-i','sine=frequency=440:sample_rate=16000',
        '-vf',f'drawbox=x=0:y=0:w=240:h=540:c=0x714047:t=fill,'
        f'drawbox=x=720:y=0:w=240:h=540:c=0x394d76:t=fill,'
        f'drawbox=x=420:y=190:w=120:h=320:c=0x73cbb5:t=fill,'
        f'drawtext=fontfile={CAPTION_FONT}:text=LEFT:fontsize=30:fontcolor=white:x=70:y=250,'
        f'drawtext=fontfile={CAPTION_FONT}:text=CENTER:fontsize=30:fontcolor=white:x=426:y=110,'
        f'drawtext=fontfile={CAPTION_FONT}:text=RIGHT:fontsize=30:fontcolor=white:x=790:y=250',
        '-t','6','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac',str(source)],
        check=True,timeout=30)
    evidence={}
    for mode in ('fit','fill-center'):
        output=folder/(mode+'.mp4');started=time.monotonic()
        info=render_excerpt(source,output,start_ms=0,end_ms=6000,frames=180,
            requested_seconds=15,max_output_bytes=64*1024**2,framing=mode,
            captions=(CaptionCue(start_ms=100,end_ms=5800,text='Check the edges.\nKeep your details.'),))
        evidence[mode]={**info,'frames':output_frames(output),'fps':30,
            'render_seconds':round(time.monotonic()-started,3),'bytes':output.stat().st_size,
            'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
    subprocess.run(['ffmpeg','-v','error','-ss','1','-i',str(folder/'fit.mp4'),
        '-ss','1','-i',str(folder/'fill-center.mp4'),'-filter_complex',
        '[0:v]scale=360:640[fit];[1:v]scale=360:640[fill];'
        '[fit][fill]hstack=inputs=2,pad=720:700:0:60:color=0x101d28,'
        f"drawtext=fontfile={CAPTION_FONT}:text='FIT FULL VIDEO':fontsize=18:fontcolor=white:x=20:y=20,"
        f"drawtext=fontfile={CAPTION_FONT}:text='FILL CENTER':fontsize=18:fontcolor=white:x=380:y=20",
        '-frames:v','1',str(folder/'comparison.png')],check=True,timeout=30)
    report={'scope':'synthetic layout/audio tone only; no face/speech acceptance',
            'results':evidence}
    (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
