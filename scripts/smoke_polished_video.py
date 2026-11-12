"""Reproducible synthetic appearance/volume proof; not ASR or human-speech QA."""
import argparse
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api'))
from app.caption_plan import CaptionCue
from app.excerpt_render import CAPTION_FONT,output_frames,render_excerpt
from app.polish import PolishSettings


def audio_rms(path):
    pcm=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-ss','2','-t','1',
        '-vn','-ar','16000','-ac','1','-f','s16le','pipe:1'])
    values=struct.unpack('<'+'h'*(len(pcm)//2),pcm)
    return round(math.sqrt(sum(v*v for v in values)/len(values)),3)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'.data/polished-video-demo')
    args=parser.parse_args();os.umask(0o077)
    folder=args.output.absolute();folder.mkdir(parents=True)
    source=folder/'synthetic-source.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=0x244654:s=960x540:r=30',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=16000','-af','volume=0.05',
        '-vf','drawbox=x=420:y=150:w=120:h=350:c=0x73cbb5:t=fill',
        '-t','6','-c:v','libx264','-threads','2','-c:a','aac',str(source)],check=True,timeout=30)
    report={'scope':'synthetic geometry/tone/manual text; no ASR, face or human-speech acceptance','results':{}}
    for name,framing,settings,text in (
        ('before','fit',PolishSettings(),'An example caption.'),
        ('polished','fill-center',PolishSettings(caption_size='large',caption_color='yellow',
            caption_position='middle',voice='level'),'Your words,\nyour style.')):
        output=folder/(name+'.mp4');start=time.monotonic()
        info=render_excerpt(source,output,start_ms=0,end_ms=6000,frames=180,requested_seconds=15,
            max_output_bytes=64*1024**2,framing=framing,polish=settings,
            captions=(CaptionCue(start_ms=200,end_ms=5800,text=text),))
        report['results'][name]={**info,'frames':output_frames(output),
            'render_seconds':round(time.monotonic()-start,3),'audio_rms':audio_rms(output)}
    subprocess.run(['ffmpeg','-v','error','-ss','1','-i',str(folder/'before.mp4'),
        '-ss','1','-i',str(folder/'polished.mp4'),'-filter_complex',
        '[0:v]scale=360:640[a];[1:v]scale=360:640[b];[a][b]hstack,pad=720:700:0:60:color=0x101d28,'
        f"drawtext=fontfile={CAPTION_FONT}:text='ORIGINAL SETTINGS':fontsize=17:fontcolor=white:x=20:y=20,"
        f"drawtext=fontfile={CAPTION_FONT}:text='POLISHED EXAMPLE':fontsize=17:fontcolor=white:x=380:y=20",
        '-frames:v','1',str(folder/'comparison.png')],check=True,timeout=30)
    (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
