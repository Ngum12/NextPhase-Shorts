"""Bounded independent documentary compositor for the consented private pilot.

Each scene is encoded in its existing native sandbox. Final composition grants
read access to exact verified intermediates, never a directory or remote URL.
The narration remains one continuous source interval. No model code is executed.
"""
import hashlib,json,math,os,re,shutil,stat,struct,subprocess,tempfile,textwrap,time
from pathlib import Path

from .documentary_plan import AssetReceipt,DocumentaryPlan,DocumentaryFailure
from .excerpt_render import CAPTION_FONT,output_frames,PREVIEW_ENCODER_PRESET
from .media import MediaCancelled,MediaError,OutputLimitExceeded,run_render,probe_video,decoder_invocation,teardown_decoder
from .media_policy import CODEC_THREADS,input_args
from .preview_framing import framing_filter

MAX_OUTPUT=64*1024**2


def checksum(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def regular(path,maximum):
    path=Path(path)
    if any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file():raise DocumentaryFailure('SOURCE_INVALID')
    stat=path.stat()
    if stat.st_nlink!=1 or not 0<stat.st_size<=maximum:raise DocumentaryFailure('SOURCE_INVALID')
    return path


def copy_verified(source,destination,expected,maximum,check):
    """Hash during the bounded copy; cancellation and deadline checked per MiB."""
    digest=hashlib.sha256();size=0
    descriptor=os.open(source,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    with os.fdopen(descriptor,'rb') as original,Path(destination).open('xb') as output:
        metadata=os.fstat(original.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink!=1:raise DocumentaryFailure('SOURCE_INVALID')
        os.chmod(destination,0o600)
        while chunk:=original.read(1048576):
            check();size+=len(chunk)
            if size>maximum:raise DocumentaryFailure('SOURCE_INVALID')
            output.write(chunk);digest.update(chunk)
    if digest.hexdigest()!=expected:raise DocumentaryFailure('SOURCE_INVALID')


def card_background(path):
    """Original flat artwork, not an external asset or fabricated evidence."""
    width,height=1080,1920;stride=width*3;pixels=bytearray()
    for y in range(height):
        shade=y/height
        row=bytearray(bytes((int(28+18*shade),int(19+14*shade),int(10+6*shade)))*width)
        if 160<y<1760:row[64*3:69*3]=bytes((192,223,88))*5
        if y in (118,1798):row[96*3:1016*3]=bytes((70,83,72))*920
        pixels.extend(row)
    header=struct.pack('<2sIHHI',b'BM',54+len(pixels),0,0,54)
    header+=struct.pack('<IiiHHIIiiII',40,width,-height,1,24,0,len(pixels),2835,2835,0,0)
    with Path(path).open('xb') as output:os.chmod(path,0o600);output.write(header);output.write(pixels)


def text_filter(text,folder,*,size,color,x,y,alpha='1'):
    lines=textwrap.wrap(text,width=23 if size>=60 else 40,break_long_words=True,break_on_hyphens=False)
    text='\n'.join(lines)
    if len(text.encode())>256:raise DocumentaryFailure('PLAN_INVALID')
    fd,name=tempfile.mkstemp(prefix='caption-',suffix='.txt',dir=folder)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:stream.write(text)
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+',name):
        Path(name).unlink(missing_ok=True);raise DocumentaryFailure('PLAN_INVALID')
    return (f'drawtext=fontfile={CAPTION_FONT}:textfile={name}:expansion=none:fontsize={size}:'
        f"fontcolor={color}:line_spacing=14:x='{x}':y='{y}':alpha='{alpha}'"),Path(name)


def image_probe(path,timeout=30):
    command=['ffprobe','-v','error','-max_alloc','67108864','-protocol_whitelist','file',
        '-format_whitelist','image2,jpeg_pipe,bmp_pipe','-codec_whitelist','mjpeg,bmp','-threads','2',
        '-select_streams','v:0','-show_entries','stream=width,height,codec_name','-of','json',str(path)]
    command,env,kwargs=decoder_invocation(command,timeout)
    with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL,env=env,**kwargs) as child:
        try:
            raw,_=child.communicate(timeout=timeout)
            if child.returncode:raise DocumentaryFailure('ASSET_UNSUPPORTED')
        finally:teardown_decoder(child)
    try:
        stream=json.loads(raw)['streams'][0];width,height=int(stream['width']),int(stream['height'])
        if stream['codec_name'] not in ('mjpeg','bmp') or not 16<=width<=4096 or not 16<=height<=4096 or width*height>8294400:raise ValueError()
    except (ValueError,KeyError,IndexError,TypeError):raise DocumentaryFailure('ASSET_UNSUPPORTED') from None


def render_documentary(source,destination,plan,assets,*,should_cancel=lambda:False,timeout=300,max_output_bytes=MAX_OUTPUT):
    """assets maps content SHA IDs to (receipt, local file); no network during render."""
    plan=DocumentaryPlan.model_validate(plan)
    if type(timeout) is not int or not 1<=timeout<=300:raise DocumentaryFailure('PLAN_INVALID')
    if type(max_output_bytes) is not int or not 1<=max_output_bytes<=MAX_OUTPUT:raise DocumentaryFailure('PLAN_INVALID')
    started=time.monotonic()
    if should_cancel():raise MediaCancelled('Documentary cancelled')
    source=regular(source,314572800);destination=Path(destination)
    if any(p.is_symlink() for p in (destination,*destination.parents)) or destination.exists():raise DocumentaryFailure('SOURCE_INVALID')
    info=probe_video(source,timeout=min(30,timeout))
    if plan.source_end_ms>math.ceil(info['duration']*1000):raise DocumentaryFailure('PLAN_INVALID')
    if len(assets)>3:raise DocumentaryFailure('PLAN_INVALID')
    bound={};total=0
    for identity,(receipt,path) in assets.items():
        receipt=AssetReceipt.model_validate(receipt);path=regular(path,16777216)
        if identity!=receipt.asset_id or path.stat().st_size!=receipt.bytes or checksum(path)!=identity:raise DocumentaryFailure('RIGHTS_UNCONFIRMED')
        total+=receipt.bytes;bound[identity]=(receipt,path)
    if total>25165824:raise DocumentaryFailure('PLAN_INVALID')
    for scene in plan.scenes:
        if scene.asset_id and (scene.asset_id not in bound or bound[scene.asset_id][0].kind!=scene.kind):raise DocumentaryFailure('PLAN_INVALID')
    destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    began=started;measurements=[]
    def remaining():
        if should_cancel():raise MediaCancelled('Documentary cancelled')
        value=timeout-(time.monotonic()-began)
        if value<=0:raise DocumentaryFailure('DEADLINE_EXCEEDED')
        return max(.01,min(60,value))
    def encode(command,limit,*,stage,scene_index=None,**kwargs):
        def guard():
            remaining()
            path=Path(command[-1])
            if path.stat().st_size>=limit:raise OutputLimitExceeded('Documentary file exceeds bound')
            return False
        start=time.monotonic()
        value=run_render(command,remaining(),guard,max_file_bytes=limit,**kwargs) or {}
        measurements.append({'stage':stage,'scene_index':scene_index,'wall_seconds':round(time.monotonic()-start,3),**value})
    try:
        with tempfile.TemporaryDirectory(prefix='documentary-',dir=destination.parent) as temporary:
            root=Path(temporary);os.chmod(root,0o700)
            original=root/'input.media';copy_verified(source,original,plan.source_sha256,314572800,remaining)
            voice=root/'voice.wav';voice.touch(mode=0o600)
            seconds=plan.output_frames/30
            # Audio is the original continuous voice; no external asset audio,
            # synthesis, reordered sentences or hidden music is mixed into it.
            encode(['ffmpeg','-nostdin','-v','error','-y','-max_alloc','67108864',*input_args(),'-i',str(original),
                '-ss',f'{plan.source_start_ms/1000:.3f}','-t',f'{seconds:.6f}','-map','0:a:0','-vn',
                '-ac','2','-ar','48000','-c:a','pcm_s16le','-map_metadata','-1',str(voice)],16777216,stage='voice')
            scenes=[]
            for index,scene in enumerate(plan.scenes):
                remaining();frames=scene.end_frame-scene.start_frame;out=root/f'scene-{index:02d}.mp4';out.touch(mode=0o600)
                files=[];receipt=None
                if scene.kind in ('image','video'):
                    receipt,path=bound[scene.asset_id];visual=root/('asset-'+receipt.asset_id+('.jpg' if receipt.kind=='image' else '.webm'))
                    if not visual.exists():
                        copy_verified(path,visual,receipt.asset_id,receipt.bytes,remaining)
                elif scene.kind=='card':visual=root/f'card-{index}.bmp';card_background(visual)
                else:visual=original
                command=['ffmpeg','-nostdin','-v','error','-y','-max_alloc','67108864','-filter_threads',str(CODEC_THREADS)]
                if scene.kind in ('image','card'):
                    image_probe(visual,timeout=min(30,remaining()))
                    command+=['-loop','1','-framerate','30','-protocol_whitelist','file','-format_whitelist','image2',
                        '-codec_whitelist','mjpeg,bmp','-threads','2','-f','image2','-pattern_type','none','-i',str(visual)]
                    denominator=max(1,frames-1)
                    zoom='1' if scene.motion=='hold' else f'1+0.065*on/{denominator}'
                    x='iw/2-iw/zoom/2'
                    if scene.motion=='drift_left':x=f'(iw-iw/zoom)*(1-on/{denominator})'
                    if scene.motion=='drift_right':x=f'(iw-iw/zoom)*on/{denominator}'
                    vf=f"scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,zoompan=z='{zoom}':x='{x}':y='ih/2-ih/zoom/2':d=1:s=1080x1920:fps=30,setsar=1,format=yuv420p"
                else:
                    if scene.kind=='video' and probe_video(visual,timeout=min(30,remaining()))['duration']<frames/30:raise DocumentaryFailure('ASSET_UNSUPPORTED')
                    command+=input_args()+['-i',str(visual)]
                    if scene.kind=='source':command+=['-ss',f'{plan.source_start_ms/1000+scene.start_frame/30:.6f}']
                    vf=framing_filter('fill-center')
                # Fixed typography and bounded fade/slide motion. Text is never
                # interpolated into filter grammar or treated as expressions.
                clock=f'max(0,t-{plan.source_start_ms/1000+scene.start_frame/30:.6f})' if scene.kind=='source' else 't'
                overlays=[('NEXT PHASE / DOCUMENTARY',22,'0x58dfc0','64','76','1')]
                if scene.heading:
                    vf+=",drawbox=x=0:y=1080:w=1080:h=840:color=black@0.45:t=fill" if scene.kind!='card' else ''
                    overlays.append((scene.heading,64,'white','96' if scene.kind=='card' else '64',"750" if scene.kind=='card' else f"h-620+24*(1-min(({clock})/0.45,1))",f'min(({clock})/0.3,1)'))
                if scene.kicker:overlays.append((scene.kicker,30,'0x58dfc0','96' if scene.kind=='card' else '64','1050' if scene.kind=='card' else 'h-350',f'min(({clock})/0.45,1)'))
                credit=('Original illustration / demo' if receipt and receipt.origin=='original' else 'Wikimedia Commons / '+('CC0' if receipt and receipt.license=='CC0-1.0' else 'Public domain'))
                if receipt:overlays.append((credit,20,'white','64','1830','1'))
                for text,size,color,x,y,alpha in overlays:
                    expression,path=text_filter(text,root,size=size,color=color,x=x,y=y,alpha=alpha);vf+=','+expression;files.append(path)
                try:
                    command+=['-map','0:v:0','-an','-sn','-dn','-vf',vf,'-frames:v',str(frames),
                        '-c:v','libx264','-threads',str(CODEC_THREADS),'-preset',PREVIEW_ENCODER_PRESET,'-crf','24','-pix_fmt','yuv420p',
                        '-map_metadata','-1','-map_chapters','-1','-movflags','+faststart',str(out)]
                    available=MAX_OUTPUT-sum(path.stat().st_size for path in scenes)
                    if available<=0:raise OutputLimitExceeded('Documentary scene budget exceeded')
                    encode(command,available,stage='scene',scene_index=index,read_files=files)
                    if output_frames(out,timeout=remaining())!=frames:raise DocumentaryFailure('RENDER_FAILED')
                finally:
                    for path in files:path.unlink(missing_ok=True)
                scenes.append(out)
            listing=root/'scene-list.ffconcat'
            listing.write_text('ffconcat version 1.0\n'+''.join(f'file {path.name}\n' for path in scenes));listing.chmod(0o600)
            output=root/'final.mp4';output.touch(mode=0o600)
            encode(['ffmpeg','-nostdin','-v','error','-y','-max_alloc','67108864','-protocol_whitelist','file',
                '-format_whitelist','concat,mov','-codec_whitelist','h264','-threads','2','-f','concat','-safe','1','-i',str(listing),
                '-protocol_whitelist','file','-format_whitelist','wav','-codec_whitelist','pcm_s16le','-threads','2','-i',str(voice),
                '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','128k','-ar','48000','-ac','2',
                '-t',f'{seconds:.6f}','-frames:v',str(plan.output_frames),'-map_metadata','-1','-map_chapters','-1',
                '-movflags','+faststart',str(output)],max_output_bytes,stage='mux',media_files=[*scenes,voice])
            metadata=probe_video(output,timeout=min(30,remaining()))
            if ((metadata['width'],metadata['height'])!=(1080,1920) or metadata['duration']>min(60,plan.requested_seconds)
                    or abs(metadata['duration']-seconds)>1/30 or output_frames(output,timeout=remaining())!=plan.output_frames):
                raise DocumentaryFailure('RENDER_FAILED')
            remaining();os.link(output,destination,follow_symlinks=False)
            return {'duration':metadata['duration'],'frames':plan.output_frames,'scene_count':len(scenes),'wall_seconds':round(time.monotonic()-began,3),
                'output_bytes':destination.stat().st_size,'measurements':measurements}
    except (MediaCancelled,OutputLimitExceeded,DocumentaryFailure):raise
    except subprocess.TimeoutExpired:raise DocumentaryFailure('DEADLINE_EXCEEDED') from None
    except (MediaError,OSError,ValueError,subprocess.SubprocessError):raise DocumentaryFailure('RENDER_FAILED') from None
