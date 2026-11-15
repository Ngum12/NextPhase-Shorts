"""Create a watchable documentary-engine proof using authored synthetic narration.

Not an app feature or a private-media processor. Default uses original procedural
illustrations. --allow-public-search explicitly tests real Commons/Wikipedia
research and requires approved network access; it never silently substitutes art.
No paid service, Gemini call, private transcript or voice cloning is used.
"""
import argparse,hashlib,json,math,os,random,struct,subprocess,sys,wave
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api'))
from app.commons_assets import CommonsResearch
from app.documentary_plan import AssetReceipt,DocumentaryPlan,DocumentaryFailure
from app.documentary_render import render_documentary,checksum
from app.media import probe_video

NARRATION=('Some moments change how we see the world. A single step on the Moon became a story told through evidence, images, and a human voice. '
    'This prototype brings those pieces together: a clear story, purposeful visuals, and motion that helps the idea land.')


def command(arguments):
    subprocess.run(arguments,check=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=90)


def illustration(path,earth=False):
    """Original stylized artwork, explicitly labeled illustration in the video."""
    width,height=720,1280;pixels=bytearray()
    for y in range(height):pixels.extend(bytes((int(22+15*y/height),int(12+12*y/height),int(5+8*y/height)))*width)
    def pixel(x,y,rgb):
        if 0<=x<width and 0<=y<height:
            i=(y*width+x)*3;pixels[i:i+3]=bytes(reversed(tuple(max(0,min(255,int(c))) for c in rgb)))
    randomizer=random.Random(11 if earth else 7)
    for _ in range(180):
        x=randomizer.randrange(width);y=randomizer.randrange(1050);light=randomizer.randint(75,215)
        pixel(x,y,(light,light,light+20))
        if light>180:pixel(x+1,y,(light//2,light//2,light//2))
    cx,cy,radius=475,520,290
    for y in range(cy-radius,cy+radius):
        for x in range(cx-radius,cx+radius):
            dx=(x-cx)/radius;dy=(y-cy)/radius;square=dx*dx+dy*dy
            if square>1:continue
            normal=math.sqrt(1-square);light=max(.1,normal*.85-dx*.35-dy*.2)
            if earth:
                land=math.sin(dx*14+dy*8)*math.cos(dy*13-dx*3)>.25
                rgb=(18+light*45,45+light*(100 if land else 50),55+light*(65 if land else 140))
            else:
                grain=randomizer.randint(-12,12);base=45+light*165+grain;rgb=(base*1.02,base,base*.94)
            pixel(x,y,rgb)
    if not earth:
        for _ in range(55):
            x=randomizer.randint(cx-radius,cx+radius);y=randomizer.randint(cy-radius,cy+radius);r=randomizer.randint(4,22)
            if (x-cx)**2+(y-cy)**2>(radius-r)**2:continue
            for yy in range(y-r,y+r):
                for xx in range(x-r,x+r):
                    distance=((xx-x)**2+(yy-y)**2)/r**2
                    if distance<1:pixel(xx,yy,(100+distance*28,101+distance*27,97+distance*25))
    bitmap=path.with_suffix('.bmp')
    header=struct.pack('<2sIHHI',b'BM',54+len(pixels),0,0,54)+struct.pack('<IiiHHIIiiII',40,width,-height,1,24,0,len(pixels),2835,2835,0,0)
    bitmap.write_bytes(header+pixels);bitmap.chmod(0o600)
    command(['ffmpeg','-nostdin','-v','error','-i',str(bitmap),'-frames:v','1','-c:v','mjpeg','-threads','1','-q:v','2',str(path)])
    path.chmod(0o600);bitmap.unlink()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--allow-public-search',action='store_true')
    parser.add_argument('--topic',default='Apollo 11 Moon')
    args=parser.parse_args();output=args.output.resolve()
    if output.exists():raise SystemExit('Choose a new output filename; existing artifacts are preserved.')
    if os.getenv('WORKER_REQUIRE_SANDBOX','false').lower()=='true':
        raise SystemExit('Synthetic narration generation is a local development demo, not a required-sandbox worker operation.')
    folder=output.parent/(output.stem+'-evidence');folder.mkdir(parents=True,mode=0o700);assets={};references=[]
    if args.allow_public_search:
        research=CommonsResearch(consented=True)
        try:
            references=research.search_context(args.topic)
            images=research.search(args.topic,kind='image')
            videos=research.search(args.topic,kind='video')
            if not images:raise DocumentaryFailure('RIGHTS_UNCONFIRMED')
            selected=images[:2]+videos[:1]
            for candidate in selected:
                receipt,path=research.download(candidate,folder/'assets');assets[receipt.asset_id]=(receipt,path)
        finally:research.close()
    else:
        for i in range(2):
            image=folder/f'illustration-{i}.jpg';illustration(image,earth=bool(i))
            receipt=AssetReceipt(asset_id=checksum(image),kind='image',origin='original',creator='NextPhase original procedural illustration',
                title='Stylized original Earth illustration' if i else 'Stylized original lunar illustration',license='CC0-1.0',
                retrieved_at=datetime.now(timezone.utc).isoformat(),bytes=image.stat().st_size,original_rights_confirmed=True)
            assets[receipt.asset_id]=(receipt,image)
    script=folder/'authored-narration.txt';script.write_text(NARRATION);script.chmod(0o600)
    voice=folder/'synthetic-demo-voice.wav'
    command(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i',f'flite=textfile={script}:voice=slt','-c:a','pcm_s16le',str(voice)])
    with wave.open(str(voice),'rb') as stream:duration=stream.getnframes()/stream.getframerate()
    if not 5<=duration<=30:raise DocumentaryFailure('SOURCE_INVALID')
    image_assets=[item for item in assets.values() if item[0].kind=='image'];first=image_assets[0][1]
    source=folder/'synthetic-source.mp4'
    command(['ffmpeg','-nostdin','-v','error','-loop','1','-framerate','30','-i',str(first),'-i',str(voice),
        '-t',f'{duration:.6f}','-vf','scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,format=yuv420p',
        '-c:v','libx264','-preset','superfast','-threads','2','-crf','24','-c:a','aac','-b:a','128k','-movflags','+faststart',str(source)])
    frames=int(min(duration,probe_video(source)['duration'])*30)-1;end_ms=math.ceil(frames*1000/30);step=frames//4
    second=next((item for item in assets.values() if item[0].kind=='video'),image_assets[-1])
    plan=DocumentaryPlan(source_sha256=checksum(source),source_start_ms=0,source_end_ms=end_ms,output_frames=frames,requested_seconds=30,
        scenes=[{'kind':'card','start_frame':0,'end_frame':step,'heading':'BEYOND THE FRAME','kicker':'A documentary engine proof'},
            {'kind':'image','start_frame':step,'end_frame':step*2,'asset_id':image_assets[0][0].asset_id,
                'motion':'push_in','heading':'A NEW PERSPECTIVE','kicker':'A moment worth telling'},
            {'kind':second[0].kind,'start_frame':step*2,'end_frame':step*3,'asset_id':second[0].asset_id,
                'motion':'drift_right' if second[0].kind=='image' else 'hold','heading':'EVIDENCE, NOT FILLER','kicker':'One continuous voice'},
            {'kind':'card','start_frame':step*3,'end_frame':frames,'heading':'MAKE EVERY SECOND COUNT','kicker':'NextPhase Shorts / prototype'}])
    metrics=render_documentary(source,output,plan,assets)
    manifest={'prototype':True,'synthetic_narration':True,'voice_engine':'local FFmpeg/CMU Flite slt (demo only)',
        'assets':[receipt.model_dump(mode='json') for receipt,path in assets.values()], 'research_sources':references,
        'live_research':args.allow_public_search,'metrics':metrics}
    (folder/'asset-manifest.json').write_text(json.dumps(manifest,indent=2));(folder/'storyboard.json').write_text(plan.model_dump_json(indent=2))
    print(json.dumps({'ok':True,'output':str(output),'frames':frames,'seconds':round(frames/30,2),
        'scene_count':len(plan.scenes),'live_research':args.allow_public_search,'evidence':str(folder)},indent=2))


if __name__=='__main__':
    try:main()
    except DocumentaryFailure as error:print(json.dumps({'ok':False,'code':error.code}));raise SystemExit(1)
    except (OSError,ValueError,subprocess.SubprocessError):print(json.dumps({'ok':False,'code':'DEMO_UNAVAILABLE'}));raise SystemExit(1)
