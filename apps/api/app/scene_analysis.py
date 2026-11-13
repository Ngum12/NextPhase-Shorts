"""Bounded sampled RGB changes, not semantic scenes or automatic edit decisions."""
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Annotated,Literal

from pydantic import Field,model_validator
from .analysis_plan import ClosedModel,Digest
from .local_transcription import regular_file
from .media import MediaCancelled,MediaError,run_render
from .media_policy import input_args
from .analysis_limits import VISUAL_TIMEOUT_SECONDS

MAX_BYTES=32768
MAX_MS=180000
WIDTH=64
HEIGHT=36
FRAME_BYTES=WIDTH*HEIGHT*3
MAX_PROXY_BYTES=3*1024**2
TIMEOUT=VISUAL_TIMEOUT_SECONDS
ADDRESS_BYTES=1024**3


class SceneUnavailable(MediaError):
    def __init__(self,issue='decode_or_resource_limit'):
        self.issue=issue
        super().__init__('Visual analysis unavailable in bounded profile')


class VisualChange(ClosedModel):
    at_ms: Annotated[int,Field(strict=True,ge=500,le=MAX_MS)]
    delta_milli: Annotated[int,Field(strict=True,ge=180,le=1000)]


class SceneAnalysis(ClosedModel):
    schema_version: Literal['scene-analysis-1']='scene-analysis-1'
    source_sha256: Digest
    source_duration_ms: Annotated[int,Field(strict=True,ge=1,le=MAX_MS)]
    status: Literal['available','unavailable']
    issue: Literal['decode_or_resource_limit','insufficient_samples'] | None=None
    method: Literal['sampled_rgb_difference']='sampled_rgb_difference'
    alignment: Literal['ffmpeg_fps_start_zero']='ffmpeg_fps_start_zero'
    sample_interval_ms: Literal[500]=500
    proxy_width: Literal[64]=64
    proxy_height: Literal[36]=36
    threshold_milli: Literal[180]=180
    minimum_gap_ms: Literal[1000]=1000
    sample_count: Annotated[int,Field(strict=True,ge=0,le=361)]
    analyzed_duration_ms: Annotated[int,Field(strict=True,ge=0,le=MAX_MS)]
    changes: tuple[VisualChange,...]=Field(max_length=180)

    @model_validator(mode='after')
    def valid(self):
        if self.status=='unavailable':
            if self.issue is None or self.sample_count or self.analyzed_duration_ms or self.changes:
                raise ValueError('Unavailable visual analysis cannot claim samples or changes')
        else:
            if (self.issue is not None or self.source_duration_ms<500 or self.sample_count<2
                    or self.sample_count>math.ceil(self.source_duration_ms/500)+1
                    or self.analyzed_duration_ms!=min(self.sample_count*500,self.source_duration_ms)):
                raise ValueError('Visual sample coverage differs')
            previous=None
            for change in self.changes:
                if (change.at_ms%500 or change.at_ms>=self.source_duration_ms
                        or change.at_ms>(self.sample_count-1)*500
                        or (previous is not None and change.at_ms-previous<1000)):
                    raise ValueError('Visual changes must be sampled, ordered and inside coverage')
                previous=change.at_ms
        if len(self.model_dump_json().encode())>MAX_BYTES:raise ValueError('Visual metadata exceeds bound')
        return self


def unavailable(*,source_sha256,source_duration_ms,issue='decode_or_resource_limit'):
    return SceneAnalysis(source_sha256=source_sha256,source_duration_ms=source_duration_ms,
        status='unavailable',issue=issue,sample_count=0,analyzed_duration_ms=0,changes=())


def read_proxy(path,*,source_sha256,source_duration_ms,should_cancel):
    path=regular_file(path,maximum=MAX_PROXY_BYTES)
    size=path.stat().st_size
    count=size//FRAME_BYTES
    if size%FRAME_BYTES or count>math.ceil(source_duration_ms/500)+1 or count>361:
        raise ValueError('Invalid visual proxy shape')
    if count<2:raise SceneUnavailable('insufficient_samples')
    if should_cancel():raise MediaCancelled('Visual analysis cancelled')
    changes=[];last_check=time.monotonic()
    with path.open('rb') as stream:
        previous=stream.read(FRAME_BYTES)
        for index in range(1,count):
            if time.monotonic()-last_check>=.25:
                if should_cancel():raise MediaCancelled('Visual analysis cancelled')
                last_check=time.monotonic()
            frame=stream.read(FRAME_BYTES)
            if len(frame)!=FRAME_BYTES:raise ValueError('Truncated visual proxy')
            delta=sum(abs(left-right) for left,right in zip(previous,frame))*1000//(FRAME_BYTES*255)
            timestamp=index*500
            if delta>=180 and timestamp<source_duration_ms:
                event=dict(at_ms=timestamp,delta_milli=delta)
                if changes and timestamp-changes[-1]['at_ms']<1000:
                    if delta>changes[-1]['delta_milli']:changes[-1]=event
                else:changes.append(event)
            previous=frame
    if should_cancel():raise MediaCancelled('Visual analysis cancelled')
    return SceneAnalysis(source_sha256=source_sha256,source_duration_ms=source_duration_ms,
        status='available',sample_count=count,analyzed_duration_ms=min(count*500,source_duration_ms),changes=tuple(changes))


def analyze(source,*,source_sha256,source_duration_ms,should_cancel=lambda:False):
    if type(source_duration_ms) is not int or not 1<=source_duration_ms<=MAX_MS:
        raise ValueError('Unsupported visual analysis duration')
    source=regular_file(source,maximum=314572800)
    if should_cancel():raise MediaCancelled('Visual analysis cancelled')
    if source_duration_ms<500:raise SceneUnavailable('insufficient_samples')
    with tempfile.TemporaryDirectory(prefix='scene-',dir=source.parent) as folder:
        output=Path(folder)/'proxy.rgb'
        with output.open('xb'):os.chmod(output,0o600)
        def stop():
            if output.stat().st_size>MAX_PROXY_BYTES:raise MediaError('Visual proxy exceeds file bound')
            return should_cancel()
        try:
            run_render(['ffmpeg','-nostdin','-v','error','-y','-max_alloc','67108864','-filter_threads','1',
                *input_args(),'-i',str(source),'-t',f'{source_duration_ms/1000:.3f}',
                '-map','0:v:0','-an','-vf','fps=2:start_time=0:round=near,scale=64:36:flags=area,format=rgb24',
                '-fps_mode','passthrough','-threads','1','-pix_fmt','rgb24','-f','rawvideo',str(output)],
                TIMEOUT,stop,max_file_bytes=MAX_PROXY_BYTES,address_limit_bytes=ADDRESS_BYTES)
            return read_proxy(output,source_sha256=source_sha256,source_duration_ms=source_duration_ms,should_cancel=should_cancel)
        except subprocess.TimeoutExpired:
            # run_render has already killed/waited for the decoder. Raw RGB is
            # fixed-size: retain only its complete prefix frames, never a partly
            # written frame or an invented estimate of the unchecked remainder.
            if should_cancel():raise MediaCancelled('Visual analysis cancelled')
            try:
                regular_file(output,maximum=MAX_PROXY_BYTES)
                complete=output.stat().st_size//FRAME_BYTES
                # The metadata reports half-second bins. Keep one decoded frame
                # as lookahead so the reported prefix cannot extend half a
                # second beyond the last frame actually decoded at timeout.
                if complete<3:raise SceneUnavailable()
                with output.open('r+b') as stream:
                    stream.truncate((complete-1)*FRAME_BYTES)
                return read_proxy(output,source_sha256=source_sha256,source_duration_ms=source_duration_ms,should_cancel=should_cancel)
            except MediaCancelled:raise
            except (SceneUnavailable,OSError,ValueError,RuntimeError):
                raise SceneUnavailable() from None
        except (MediaCancelled,SceneUnavailable):raise
        except (MediaError,OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            raise SceneUnavailable() from None
