"""Independent, frame-exact documentary composition contract; never executable AI code.

Research and rendering are separate boundaries. Scene asset IDs resolve only to
verified local receipts; URLs cannot become renderer inputs. Used by the consented pilot.
"""
import re
from typing import Literal
from urllib.parse import urlsplit
from pydantic import Field,model_validator
from .analysis_plan import ClosedModel,Digest


class DocumentaryFailure(RuntimeError):
    CODES={'CONSENT_REQUIRED','RESEARCH_UNAVAILABLE','ASSET_UNSUPPORTED','RIGHTS_UNCONFIRMED',
        'DOWNLOAD_REJECTED','SOURCE_INVALID','PLAN_INVALID','RENDER_FAILED','DEADLINE_EXCEEDED'}
    def __init__(self,code):
        if code not in self.CODES:raise ValueError('Unknown documentary failure')
        self.code=code;super().__init__('Documentary production is unavailable')


def safe_text(value,maximum):
    return isinstance(value,str) and 0<len(value)<=maximum and not any(ord(c)<32 or ord(c)==127 for c in value)


def commons_url(value,host,prefix):
    if not isinstance(value,str) or len(value)>2048 or any(c.isspace() or ord(c)<32 for c in value):return False
    parsed=urlsplit(value)
    return (parsed.scheme=='https' and parsed.hostname==host and parsed.port in (None,443)
        and parsed.username is None and parsed.password is None and not parsed.fragment
        and not parsed.query and parsed.path.startswith(prefix) and '\\' not in value)


class AssetReceipt(ClosedModel):
    asset_id: Digest
    kind: Literal['image','video']
    origin: Literal['commons','original']
    creator: str=Field(min_length=1,max_length=500)
    title: str=Field(min_length=1,max_length=300)
    license: Literal['CC0-1.0','public-domain']
    source_url: str | None=None
    download_url: str | None=None
    retrieved_at: str=Field(min_length=1,max_length=40)
    bytes: int=Field(strict=True,ge=1,le=16777216)
    # Only original demo assets use this explicit ownership assertion. Provider
    # assets carry source metadata, not a claim of universal legal clearance.
    original_rights_confirmed: bool=Field(default=False,strict=True)

    @model_validator(mode='after')
    def provenance(self):
        if not safe_text(self.creator,500) or not safe_text(self.title,300):raise ValueError('Invalid credit')
        if self.kind=='image' and self.bytes>8388608:raise ValueError('Image exceeds bound')
        if self.origin=='commons':
            if (not self.source_url or not commons_url(self.source_url,'commons.wikimedia.org','/wiki/File:') or
                not self.download_url or not commons_url(self.download_url,'upload.wikimedia.org','/wikipedia/commons/')):
                raise ValueError('Untrusted asset origin')
        elif not self.original_rights_confirmed or self.source_url is not None or self.download_url is not None:
            raise ValueError('Original asset rights must be explicit')
        return self


class DocumentaryScene(ClosedModel):
    kind: Literal['source','image','video','card']
    start_frame: int=Field(strict=True,ge=0,lt=1800)
    end_frame: int=Field(strict=True,gt=0,le=1800)
    asset_id: Digest | None=None
    motion: Literal['hold','push_in','drift_left','drift_right']='hold'
    heading: str=Field(default='',max_length=53)
    kicker: str=Field(default='',max_length=53)

    @model_validator(mode='after')
    def closed_scene(self):
        if not 30<=self.end_frame-self.start_frame<=450:raise ValueError('Scene must be 1–15 seconds')
        if self.kind in ('source','video') and self.motion!='hold':raise ValueError('Unsupported source motion')
        if (self.kind in ('image','video'))!=(self.asset_id is not None):raise ValueError('Scene asset differs')
        for text in (self.heading,self.kicker):
            if text and (not safe_text(text,53) or len(text.encode())>212):raise ValueError('Invalid scene text')
        return self


class DocumentaryPlan(ClosedModel):
    schema_version: Literal['documentary-scenes-1']='documentary-scenes-1'
    source_sha256: Digest
    source_start_ms: int=Field(strict=True,ge=0,lt=600000)
    source_end_ms: int=Field(strict=True,gt=0,le=600000)
    output_frames: int=Field(strict=True,ge=150,le=1800)
    requested_seconds: int=Field(strict=True,ge=5,le=60)
    scenes: tuple[DocumentaryScene,...]=Field(min_length=2,max_length=8)

    @model_validator(mode='after')
    def timeline(self):
        span=self.source_end_ms-self.source_start_ms
        if not 5000<=span<=self.requested_seconds*1000 or self.output_frames!=span*30//1000:
            raise ValueError('Voice interval differs from output')
        cursor=0
        for scene in self.scenes:
            if scene.start_frame!=cursor:raise ValueError('Scene timeline has a gap or overlap')
            cursor=scene.end_frame
        if cursor!=self.output_frames or self.output_frames>self.requested_seconds*30:
            raise ValueError('Scene timeline differs from output')
        return self
