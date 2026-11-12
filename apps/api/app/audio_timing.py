"""Bounded low-energy intervals in normalized analysis PCM, not speech VAD.

Only numbers are retained. No source audio edits or automatic cut decisions.
"""
from array import array
import sys
import time
from typing import Annotated,Literal
import wave

from pydantic import Field,model_validator
from .analysis_plan import ClosedModel,Digest
from .local_transcription import regular_file
from .media import MediaCancelled

MAX_BYTES=32768
MAX_MS=180000
FRAME_RATE=16000
WINDOW_FRAMES=320
# (-40 dBFS)^2 relative to signed 16-bit full scale; integer comparison.
QUIET_MEAN_SQUARE=107374


class QuietInterval(ClosedModel):
    start_ms: Annotated[int,Field(strict=True,ge=0,le=MAX_MS)]
    end_ms: Annotated[int,Field(strict=True,ge=1,le=MAX_MS)]

    @model_validator(mode='after')
    def valid(self):
        if self.end_ms-self.start_ms<500:raise ValueError('Quiet interval is too short')
        return self


class AudioTiming(ClosedModel):
    schema_version: Literal['audio-timing-1']='audio-timing-1'
    source_sha256: Digest
    source_duration_ms: Annotated[int,Field(strict=True,ge=1,le=MAX_MS)]
    audio_duration_ms: Annotated[int,Field(strict=True,ge=1,le=MAX_MS)]
    alignment: Literal['normalized_pcm_first_pts_zero']='normalized_pcm_first_pts_zero'
    method: Literal['pcm_window_energy']='pcm_window_energy'
    window_ms: Literal[20]=20
    threshold_dbfs: Literal[-40]=-40
    minimum_quiet_ms: Literal[500]=500
    quiet_intervals: tuple[QuietInterval,...]=Field(max_length=360)

    @model_validator(mode='after')
    def valid(self):
        if self.audio_duration_ms>self.source_duration_ms:raise ValueError('Audio exceeds source')
        cursor=0
        for interval in self.quiet_intervals:
            if interval.start_ms<cursor or interval.end_ms>self.audio_duration_ms:
                raise ValueError('Quiet intervals must be ordered inside audio')
            cursor=interval.end_ms
        if len(self.model_dump_json().encode())>MAX_BYTES:raise ValueError('Audio timing exceeds metadata bound')
        return self


def analyze(audio,*,source_sha256,source_duration_ms,should_cancel=lambda:False):
    if type(source_duration_ms) is not int or not 1<=source_duration_ms<=MAX_MS:
        raise ValueError('Unsupported audio timing duration')
    path=regular_file(audio,maximum=MAX_MS*32+4096)
    if should_cancel():raise MediaCancelled('Audio timing cancelled')
    quiet=[];run_start=None;position=0;last_check=time.monotonic()
    with wave.open(str(path),'rb') as wav:
        count=wav.getnframes()
        if ((wav.getnchannels(),wav.getsampwidth(),wav.getframerate())!=(1,2,FRAME_RATE)
                or not 0<count<=source_duration_ms*16):raise ValueError('Unexpected timing PCM profile')
        def finish(end):
            nonlocal run_start
            if run_start is not None:
                start_ms=run_start//16;end_ms=end//16
                if end_ms-start_ms>=500:quiet.append(dict(start_ms=start_ms,end_ms=end_ms))
                run_start=None
        while position<count:
            if time.monotonic()-last_check>=.25:
                if should_cancel():raise MediaCancelled('Audio timing cancelled')
                last_check=time.monotonic()
            raw=wav.readframes(min(WINDOW_FRAMES,count-position))
            if not raw or len(raw)%2:raise ValueError('Truncated timing PCM')
            samples=array('h',raw)
            if sys.byteorder!='little':samples.byteswap()
            low=sum(value*value for value in samples)<=len(samples)*QUIET_MEAN_SQUARE
            if low:
                if run_start is None:run_start=position
            else:finish(position)
            position+=len(samples)
        finish(position)
        if position!=count:raise ValueError('Timing PCM length differs')
    if should_cancel():raise MediaCancelled('Audio timing cancelled')
    return AudioTiming(source_sha256=source_sha256,source_duration_ms=source_duration_ms,
        audio_duration_ms=(count+15)//16,quiet_intervals=tuple(quiet))
