"""Bounded baseline input profile. Not antivirus, legal clearance or a sandbox."""
import math
from fractions import Fraction

POLICY_VERSION='baseline-media-v1'
VIDEO_CODECS={'h264','hevc','vp8','vp9','av1','mpeg4','mjpeg'}
AUDIO_CODECS={'aac','mp3','opus','vorbis','flac','alac','pcm_s16le','pcm_s24le','pcm_s32le',
              'pcm_f32le','pcm_s16be','pcm_s24be','pcm_s32be'}
DECODER_ALIASES={'libdav1d','libaom-av1','libvpx','libvpx-vp9','libopus','libvorbis','mp3float','aac_fixed'}
MOV_NAMES={'mov','mp4','m4a','3gp','3g2','mj2'}
MATROSKA_NAMES={'matroska','webm'}
MAX_PIXELS=3840*2160
MAX_STREAMS=8
CODEC_THREADS=2


def input_args():
    return ['-protocol_whitelist','file','-format_whitelist','mov,matroska,webm',
            '-codec_whitelist',','.join(sorted(VIDEO_CODECS|AUDIO_CODECS|DECODER_ALIASES)),
            '-threads',str(CODEC_THREADS),'-max_streams',str(MAX_STREAMS),'-probesize','10485760','-analyzeduration','5000000']


def validate_metadata(data):
    format_info=data['format'];names=set(format_info['format_name'].split(','))
    if not names or not (names<=MOV_NAMES or names<=MATROSKA_NAMES):raise ValueError('Unsupported container')
    duration=float(format_info['duration'])
    if not math.isfinite(duration) or not 0<duration<86400:raise ValueError('Invalid duration')
    streams=data['streams']
    if not isinstance(streams,list) or not 1<=len(streams)<=MAX_STREAMS:raise ValueError('Too many streams')
    videos=[stream for stream in streams if stream['codec_type']=='video']
    audio=[stream for stream in streams if stream['codec_type']=='audio']
    if len(videos)!=1 or len(audio)>1:raise ValueError('Use one video and at most one audio track')
    video=videos[0]
    if video['codec_name'] not in VIDEO_CODECS or video.get('disposition',{}).get('attached_pic',0):
        raise ValueError('Unsupported video track')
    width,height=int(video['width']),int(video['height'])
    if not (16<=width<=7680 and 16<=height<=7680) or width*height>MAX_PIXELS:
        raise ValueError('Video exceeds the source pixel limit')
    rates=[Fraction(video[key]) for key in ('avg_frame_rate','r_frame_rate')
           if video.get(key) not in (None,'0/0','0/1')]
    if not rates or any(not 0<fps<=120 for fps in rates):raise ValueError('Unsupported frame rate')
    for stream in audio:
        if stream['codec_name'] not in AUDIO_CODECS or not 1<=int(stream['channels'])<=8:
            raise ValueError('Unsupported audio track')
        if not 8000<=int(stream['sample_rate'])<=96000:raise ValueError('Unsupported audio sample rate')
    return {'duration':duration,'width':width,'height':height}
