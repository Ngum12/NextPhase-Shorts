"""Immutable queue metadata and bounded verified source copies for local previews."""
import hashlib
import math
import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator
from sqlalchemy import select

from .analysis_plan import ClosedModel, Digest, Milliseconds
from .config import get_settings
from .db import SessionLocal
from .media import MediaCancelled, MediaError, probe_video
from .models import RenderJob
from .caption_plan import CaptionCue, validate_cues
from .preview_framing import Framing
from .polish import PolishSettings


class ExcerptSpec(ClosedModel):
    schema_version: Literal['excerpt-1']='excerpt-1'
    source_sha256: Digest
    source_bytes: Annotated[int,Field(strict=True,ge=1,le=314572800)]
    source_duration_ms: Annotated[int,Field(strict=True,ge=1,le=600000)]
    source_extension: Literal['.mp4','.mov','.m4v','.webm']
    source_start_ms: Milliseconds
    source_end_ms: Milliseconds
    output_frames: Annotated[int,Field(strict=True,ge=150,le=1800)]
    requested_seconds: Annotated[int,Field(strict=True,ge=5,le=60)]
    review_sha256: Digest
    transcript_sha256: Digest
    review_revision: Digest
    candidate_number: Annotated[int,Field(strict=True,ge=1,le=5)]
    caption_style: Literal['none','clean-1']='none'
    captions: tuple[CaptionCue,...] = Field(default=(), max_length=80)
    framing: Framing='fit'
    polish: PolishSettings=Field(default_factory=PolishSettings)
    caption_edits_applied: bool=Field(default=False,strict=True)

    @model_validator(mode='after')
    def valid(self):
        validate_cues(self.captions, self.output_frames)
        if (self.caption_style == 'clean-1') != bool(self.captions):
            raise ValueError('Caption style and cues disagree')
        if self.caption_edits_applied and not self.captions:
            raise ValueError('Caption edits need captions')
        duration=self.source_end_ms-self.source_start_ms
        if (not 0<duration<=self.requested_seconds*1000
                or self.source_end_ms>self.source_duration_ms
                or self.output_frames!=duration*30//1000):
            raise ValueError('Invalid excerpt interval')
        return self


def snapshot_source(job,destination,*,should_cancel,spec=None):
    """Never let the decoder follow a client path or read an unchecked original."""
    spec=spec or ExcerptSpec.model_validate_json(job['preview_spec_json'])
    with SessionLocal() as db:
        parent=db.scalar(select(RenderJob).where(RenderJob.id==job['preview_parent_id'],
            RenderJob.user_id==job['user_id'],RenderJob.status!='deleted',
            RenderJob.deleted_at.is_(None),RenderJob.preview_parent_id.is_(None)))
        if parent is None:raise MediaCancelled('Preview source was deleted')
        if parent.media_backend!='local':raise MediaError('Preview source profile differs')
        source=get_settings().storage_dir/job['user_id']/parent.id/('input'+spec.source_extension)
        if Path(parent.source_path).absolute()!=source.absolute():raise MediaError('Preview source identity differs')
    for path in (source,*source.parents,destination.parent,*destination.parent.parents):
        if path.is_symlink() or getattr(path,'is_junction',lambda:False)():
            raise MediaError('Unsafe preview source')
    destination.parent.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    destination.parent.mkdir(mode=0o700,exist_ok=True)
    digest=hashlib.sha256();size=0
    descriptor=os.open(source,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        with os.fdopen(descriptor,'rb') as original,destination.open('xb') as copied:
            os.chmod(destination,0o600)
            while chunk:=original.read(1024**2):
                if should_cancel():raise MediaCancelled('Preview cancelled during copy')
                size+=len(chunk)
                if size>spec.source_bytes:raise MediaError('Preview source size differs')
                copied.write(chunk);digest.update(chunk)
        if size!=spec.source_bytes or digest.hexdigest()!=spec.source_sha256:
            raise MediaError('Preview source checksum differs')
        metadata=probe_video(destination)
        if math.ceil(metadata['duration']*1000)!=spec.source_duration_ms:
            raise MediaError('Preview source duration differs')
        if should_cancel():raise MediaCancelled('Preview cancelled after copy')
        return spec
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
