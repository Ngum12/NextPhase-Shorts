"""Owner-bound documentary admission, durable no-repeat provider claims and receipts."""
import hashlib,json,time,uuid
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Response
from pydantic import Field,model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from .analysis_plan import ClosedModel,Digest
from .analysis_annotations import fingerprint
from .auth import current_user
from .config import get_settings
from .db import SessionLocal,session_dep
from .models import RenderJob,ProjectAnalysis,UploadSession,User,utcnow
from .project_analysis import owned_project,document,PRIVATE
from .gemini_selection import available,budget
from .automatic_clips import for_project
from .queue import admit_job,lock_owner
from .schemas import JobResponse
from .documentary_director import Direction

router=APIRouter(prefix='/api/v1/jobs',tags=['Private documentary pilot'])
CONSENT='documentary-research-v1'
MIB=1024**2


class DocumentarySpec(ClosedModel):
    schema_version: Literal['documentary-job-1']='documentary-job-1'
    source_sha256: Digest
    source_bytes: int=Field(strict=True,ge=1,le=300*MIB)
    source_duration_ms: int=Field(strict=True,ge=1,le=180000)
    source_extension: Literal['.mp4','.mov','.m4v','.webm']
    source_start_ms: int=Field(strict=True,ge=0)
    source_end_ms: int=Field(strict=True,gt=0)
    output_frames: int=Field(strict=True,ge=150,le=1800)
    requested_seconds: int=Field(strict=True,ge=5,le=60)
    transcript_sha256: Digest
    review_revision: Digest
    first_word: int=Field(strict=True,ge=0,le=999)
    last_word: int=Field(strict=True,ge=0,le=999)
    consent_version: Literal['documentary-research-v1']=CONSENT
    consent_at: int=Field(strict=True,ge=0)
    model: Literal['gemini-3.1-flash-lite']='gemini-3.1-flash-lite'
    direction_started: bool=Field(default=False,strict=True)
    direction: Direction|None=None
    visuals_started: bool=Field(default=False,strict=True)
    # Receipts/scene plan live with the private attempt; no provider raw text.
    usage: tuple[dict,...]=Field(default=(),max_length=2)

    @model_validator(mode='after')
    def bounds(self):
        span=self.source_end_ms-self.source_start_ms
        if (not 5000<=span<=self.requested_seconds*1000 or self.source_end_ms>self.source_duration_ms or
            self.output_frames!=span*30//1000 or self.first_word>self.last_word):raise ValueError('Invalid documentary interval')
        if self.direction is not None and not self.direction_started:raise ValueError('Direction claim missing')
        if self.visuals_started and self.direction is None:raise ValueError('Direction missing')
        for entry in self.usage:
            if not isinstance(entry,dict) or set(entry)!={'wall_ms','input_tokens','output_tokens'}:raise ValueError('Invalid usage')
            for key,value in entry.items():
                if value is not None and (type(value) is not int or not 0<=value<=10000000):raise ValueError('Invalid usage')
        return self


class DocumentaryRequest(ClosedModel):
    consent_version: Literal['documentary-research-v1']
    acknowledged_google_transcript_sharing: bool=Field(strict=True)
    acknowledged_public_research: bool=Field(strict=True)
    @model_validator(mode='after')
    def consent(self):
        if not self.acknowledged_google_transcript_sharing or not self.acknowledged_public_research:
            raise ValueError('Explicit Google and public research consent is required')
        return self


@router.post('/{job_id}/analysis/documentary',status_code=202)
def create(job_id:str,payload:DocumentaryRequest,response:Response,user:User=Depends(current_user),db:Session=Depends(session_dep)):
    parent=owned_project(db,user.id,job_id);response.headers.update(PRIVATE)
    if parent.preview_parent_id is not None or parent.media_backend!='local':
        raise HTTPException(409,'Use an original local recording',headers=PRIVATE)
    key='documentary_'+parent.id
    old=db.scalar(select(RenderJob).where(RenderJob.user_id==user.id,RenderJob.idempotency_key==key))
    # One documentary per accepted source; even retries/restarts cannot spend again.
    if old:
        if old.status=='deleted':raise HTTPException(410,'This documentary was deleted. Use a new source project.',headers=PRIVATE)
        result=JobResponse.model_validate(old).model_dump(mode='json');db.commit();return result
    from .automatic_analysis import enabled
    if not available(user.id) or not enabled(user.id):raise HTTPException(409,'Documentary requires the configured free-tier Gemini pilot',headers=PRIVATE)
    if parent.source_duration_seconds>180:
        raise HTTPException(422,'Documentary currently supports English recordings up to three minutes',headers=PRIVATE)
    row=db.get(ProjectAnalysis,parent.id)
    if row is None:raise HTTPException(409,'Wait for English speech analysis before creating a documentary',headers=PRIVATE)
    document(row);base=for_project(row,parent)
    if not base.candidates:raise HTTPException(409,'No complete spoken excerpt fits this duration',headers=PRIVATE)
    accepted=db.scalar(select(UploadSession).where(UploadSession.job_id==parent.id,
        UploadSession.user_id==user.id,UploadSession.status=='completed'))
    if not accepted or not 0<accepted.total_bytes<=min(get_settings().max_upload_bytes,300*MIB) or accepted.source_sha256!=base.source_sha256:raise HTTPException(409,'Accepted source is unavailable',headers=PRIVATE)
    candidate=base.candidates[0]
    spec=DocumentarySpec(source_sha256=base.source_sha256,source_bytes=accepted.total_bytes,
        source_duration_ms=base.source_duration_ms,source_extension=Path(parent.source_path).suffix.lower(),
        source_start_ms=candidate.source_start_ms,source_end_ms=candidate.source_end_ms,output_frames=candidate.output_frames,
        requested_seconds=parent.desired_seconds,transcript_sha256=base.transcript_sha256,review_revision=fingerprint(base),
        first_word=candidate.first_word,last_word=candidate.last_word,consent_at=int(time.time()))
    from .budget_control import require_open
    require_open()
    # Reserve two calls in the same durable daily ledger as Gemini selection.
    # Committed failures consume the allowance; rejected admission rolls it back.
    for _ in range(2):
        if not budget(db,user.id):
            raise HTTPException(429,'The free-tier planning allowance is full. Try another day.',headers=PRIVATE)
        db.flush()  # Session disables autoflush; the next reservation must see this call.
    cap=min(get_settings().max_render_bytes,64*MIB)
    # Two attempt directories: source snapshot+compositor copy, assets and their verified copies,
    # voice16, scenes64, output cap; private receipts/plan bounded separately.
    reserved=2*(2*spec.source_bytes+(48+16+64+1)*MIB+cap)
    child=RenderJob(id=str(uuid.uuid4()),user_id=user.id,title=parent.title[:80]+' · documentary',operation='preview',
        style='documentary',desired_seconds=parent.desired_seconds,source_duration_seconds=parent.source_duration_seconds,
        source_path='',media_backend='local',status='queued',rights_version=parent.rights_version,
        rights_confirmed_at=parent.rights_confirmed_at,max_render_bytes=cap,storage_reserved_bytes=reserved,
        preview_parent_id=parent.id,preview_spec_json=spec.model_dump_json(),idempotency_key=key,
        request_hash=hashlib.sha256((parent.id+':'+CONSENT).encode()).hexdigest())
    child,_=admit_job(db,child);result=JobResponse.model_validate(child).model_dump(mode='json');db.commit();return result


def checkpoint(job,change):
    """Fence every durable provider claim/result against deletion, expiry and takeover."""
    from .media import MediaCancelled
    with SessionLocal.begin() as db:
        lock_owner(db,job['user_id'],allow_deleted=True);now=utcnow()
        child=db.scalar(select(RenderJob).where(RenderJob.id==job['id'],RenderJob.user_id==job['user_id'],
            RenderJob.status=='processing',RenderJob.claim_token==job['claim_token'],
            RenderJob.lease_expires_at>now,RenderJob.claim_deadline_at>now).with_for_update())
        parent=db.get(RenderJob,job['preview_parent_id'])
        if not child or not parent or parent.user_id!=job['user_id'] or parent.deleted_at is not None or parent.status=='deleted':
            raise MediaCancelled('Documentary claim revoked')
        spec=DocumentarySpec.model_validate_json(child.preview_spec_json)
        updated=change(spec)
        child.preview_spec_json=DocumentarySpec.model_validate(updated).model_dump_json()
        return DocumentarySpec.model_validate_json(child.preview_spec_json)


@router.get('/{job_id}/documentary-sources')
def sources(job_id:str,response:Response,user:User=Depends(current_user),db:Session=Depends(session_dep)):
    job=owned_project(db,user.id,job_id);response.headers.update(PRIVATE)
    if job.status!='succeeded' or not job.preview_spec_json or json.loads(job.preview_spec_json).get('schema_version')!='documentary-job-1':
        raise HTTPException(404,'Documentary sources are not ready',headers=PRIVATE)
    # Derive private canonical attempt location; never read a client/raw DB path.
    root=get_settings().storage_dir/user.id/job.id/job.claim_token
    path=root/'documentary-sources.json'
    try:
        if any(p.is_symlink() for p in (path,*path.parents)) or path.stat().st_size>65536:raise ValueError()
        data=json.loads(path.read_text())
        from .documentary_plan import AssetReceipt
        receipts=[AssetReceipt.model_validate(r).model_dump(mode='json') for r in data['assets']]
        if len(receipts)>3:raise ValueError()
    except (OSError,ValueError,TypeError,KeyError):raise HTTPException(404,'Documentary sources are unavailable',headers=PRIVATE) from None
    db.commit();return {'assets':receipts,'claims_verified':False}
