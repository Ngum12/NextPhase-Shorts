"""Private opt-in English analysis jobs in the existing fenced render queue."""
import hashlib
import math
from pathlib import Path
from typing import Annotated,Literal
import uuid

from fastapi import APIRouter,Depends,HTTPException,Response
from pydantic import Field,UUID4
from sqlalchemy import select,func,update
from sqlalchemy.orm import Session

from .analysis_plan import ClosedModel,Digest
from .config import get_settings
from .db import SessionLocal,session_dep
from .auth import current_user
from .models import RenderJob,RenderAttempt,UploadSession,ProjectAnalysis,User,utcnow
from .project_analysis import owned_project,PRIVATE,MAX_OWNER_ROWS,MAX_GLOBAL_ROWS
from .queue import lock_owner,admit_job
from .schemas import JobResponse

router=APIRouter(prefix='/api/v1/english-analysis',tags=['Private English analysis'])
MAX_SECONDS=180
SCRATCH_CAP=40*1024**2


class AnalysisSpec(ClosedModel):
    schema_version: Literal['analysis-1']='analysis-1'
    source_sha256: Digest
    source_bytes: Annotated[int,Field(strict=True,ge=1,le=314572800)]
    source_duration_ms: Annotated[int,Field(strict=True,ge=1,le=MAX_SECONDS*1000)]
    source_extension: Literal['.mp4','.mov','.webm','.m4v']
    model_sha256: Digest


def enabled(owner):
    settings=get_settings()
    return settings.english_analysis_enabled and settings.english_review_enabled and settings.media_backend=='local' and owner in settings.english_review_user_ids


def require_enabled(owner):
    if not enabled(owner):raise HTTPException(404,'Automatic English analysis is unavailable',headers=PRIVATE)


def current_task(db,parent):
    return db.scalar(select(RenderJob).where(RenderJob.preview_parent_id==parent,
        RenderJob.operation=='analysis',RenderJob.status!='deleted').order_by(RenderJob.created_at.desc(),RenderJob.id.desc()).limit(1))


def state(db,parent):
    ready=db.get(ProjectAnalysis,parent.id) is not None
    task=current_task(db,parent.id)
    upload=db.scalar(select(UploadSession).where(UploadSession.job_id==parent.id,UploadSession.status=='completed'))
    eligible=parent.preview_parent_id is None and parent.media_backend=='local' and parent.source_duration_seconds<=MAX_SECONDS and upload is not None
    return {'source_id':parent.id,'ready':ready,'eligible':eligible,
        'requested':bool(upload and upload.english_analysis),
        'task':JobResponse.model_validate(task).model_dump(mode='json') if task else None}


def enqueue(db,parent,*,key,retry=False):
    require_enabled(parent.user_id)
    if parent.preview_parent_id is not None or parent.media_backend!='local':
        raise HTTPException(409,'Use an original local-upload project',headers=PRIVATE)
    if parent.source_duration_seconds>MAX_SECONDS:
        raise HTTPException(422,'English analysis currently supports recordings up to three minutes',headers=PRIVATE)
    request_key='analysis_'+str(key)
    identity=hashlib.sha256((parent.id+':en:'+get_settings().english_analysis_model_sha256).encode()).hexdigest()
    existing=db.scalar(select(RenderJob).where(RenderJob.user_id==parent.user_id,RenderJob.idempotency_key==request_key))
    if existing:
        if existing.status=='deleted':raise HTTPException(410,'Analysis task was deleted. Start a new request.',headers=PRIVATE)
        if existing.request_hash!=identity:raise HTTPException(409,'Analysis configuration changed. Start a fresh request.',headers=PRIVATE)
        return existing
    if db.get(ProjectAnalysis,parent.id) is not None:return None
    previous=current_task(db,parent.id)
    if previous and (previous.status in ('queued','processing','succeeded') or not retry):return previous
    accepted=db.scalar(select(UploadSession).where(UploadSession.job_id==parent.id,
        UploadSession.user_id==parent.user_id,UploadSession.status=='completed'))
    if not accepted or not accepted.source_sha256:raise HTTPException(409,'Accepted upload identity is unavailable',headers=PRIVATE)
    spec=AnalysisSpec(source_sha256=accepted.source_sha256,source_bytes=accepted.total_bytes,
        source_duration_ms=math.ceil(parent.source_duration_seconds*1000),source_extension=Path(parent.source_path).suffix.lower(),
        model_sha256=get_settings().english_analysis_model_sha256)
    # Model is shared read-only; reserve verified source copies plus PCM/JSON
    # scratch for both bounded attempts, without charging a model copy per job.
    from .capacity import lock
    lock(db)
    rows=db.scalar(select(func.count()).select_from(ProjectAnalysis))
    own=db.scalar(select(func.count()).select_from(ProjectAnalysis).join(RenderJob,RenderJob.id==ProjectAnalysis.job_id).where(RenderJob.user_id==parent.user_id))
    pending=list(db.execute(select(RenderJob.user_id,RenderJob.preview_parent_id).where(
        RenderJob.operation=='analysis',RenderJob.status.in_(('queued','processing')))))
    if rows+len(pending)>=MAX_GLOBAL_ROWS or own+sum(owner==parent.user_id for owner,_ in pending)>=MAX_OWNER_ROWS:
        raise HTTPException(429,'English analysis storage is full. Delete an unneeded prepared project.',headers=PRIVATE)
    child=RenderJob(id=str(uuid.uuid4()),user_id=parent.user_id,title=parent.title[:90]+' · English',
        style=parent.style,operation='analysis',desired_seconds=parent.desired_seconds,
        source_duration_seconds=parent.source_duration_seconds,source_path='',media_backend='local',status='queued',
        rights_version=parent.rights_version,rights_confirmed_at=parent.rights_confirmed_at,
        max_render_bytes=SCRATCH_CAP,storage_reserved_bytes=2*(spec.source_bytes+SCRATCH_CAP),
        preview_parent_id=parent.id,preview_spec_json=spec.model_dump_json(),idempotency_key=request_key,request_hash=identity)
    child,_=admit_job(db,child)
    return child


def enqueue_requested(db,parent,upload):
    if not upload.english_analysis or not enabled(parent.user_id):return
    try:
        with db.begin_nested():enqueue(db,parent,key=uuid.UUID(upload.id))
    except HTTPException as error:
        if error.status_code in (409,422):upload.english_analysis=False
        # Keep accepted media; retry bounded capacity admission via supervisor.


def reconcile_requested(limit=10):
    if not get_settings().english_analysis_enabled:return 0
    with SessionLocal() as db:
        from sqlalchemy.orm import aliased
        child=aliased(RenderJob)
        ever_requested=select(child.id).where(child.preview_parent_id==RenderJob.id,child.operation=='analysis').exists()
        identities=list(db.execute(select(UploadSession.job_id,UploadSession.user_id,UploadSession.id)
            .join(RenderJob,RenderJob.id==UploadSession.job_id).outerjoin(ProjectAnalysis,ProjectAnalysis.job_id==RenderJob.id)
            .where(UploadSession.english_analysis.is_(True),UploadSession.status=='completed',RenderJob.deleted_at.is_(None),
                   RenderJob.status!='deleted',ProjectAnalysis.job_id.is_(None),~ever_requested)
            .order_by(UploadSession.created_at.desc()).limit(limit)))
    count=0
    for parent_id,owner,upload_id in identities:
        if not enabled(owner):continue
        try:
            with SessionLocal.begin() as db:
                lock_owner(db,owner)
                # The inventory read precedes this owner lock. Cancellation may
                # have cleared consent in between: never enqueue that stale read.
                intent=db.get(UploadSession,upload_id)
                if not intent or not intent.english_analysis or intent.status!='completed' or intent.job_id!=parent_id:continue
                parent=owned_project(db,owner,parent_id)
                enqueue(db,parent,key=uuid.UUID(upload_id));count+=1
        except HTTPException:continue
    return count


@router.get('/capabilities')
def capabilities(response:Response,user:User=Depends(current_user)):
    response.headers.update(PRIVATE)
    return {'available':bool(enabled(user.id)),'language':'en','max_source_seconds':MAX_SECONDS,
        'human_review_required':True,'automatic_clips':True}


class StartAnalysis(ClosedModel):
    idempotency_key: UUID4
    acknowledged_server_analysis: bool=Field(strict=True)
    retry_failed: bool=Field(default=False,strict=True)


@router.get('/jobs/{job_id}')
def get_state(job_id:str,response:Response,user:User=Depends(current_user),db:Session=Depends(session_dep)):
    require_enabled(user.id);parent=owned_project(db,user.id,job_id)
    result=state(db,parent);response.headers.update(PRIVATE);db.commit();return result


@router.post('/jobs/{job_id}',status_code=202)
def start(job_id:str,payload:StartAnalysis,response:Response,user:User=Depends(current_user),db:Session=Depends(session_dep)):
    require_enabled(user.id)
    if not payload.acknowledged_server_analysis:raise HTTPException(422,'Confirm server transcription first',headers=PRIVATE)
    from .auth_limits import consume_limits
    consume_limits([('english-analysis-owner',user.id,60)])
    parent=owned_project(db,user.id,job_id)
    enqueue(db,parent,key=payload.idempotency_key,retry=payload.retry_failed)
    result=state(db,parent);response.headers.update(PRIVATE);db.commit();return result


@router.post('/jobs/{job_id}/cancel')
def cancel(job_id:str,response:Response,user:User=Depends(current_user),db:Session=Depends(session_dep)):
    require_enabled(user.id);parent=owned_project(db,user.id,job_id)
    db.execute(update(UploadSession).where(UploadSession.job_id==parent.id,UploadSession.user_id==user.id)
        .values(english_analysis=False))
    task=current_task(db,parent.id)
    if task and task.status in ('queued','processing'):
        # Keep the old hard deadline for safe cleanup, while revoking publication.
        task.status='cancelled';task.claim_token=None;task.lease_expires_at=None;task.finished_at=utcnow()
        db.execute(update(RenderAttempt).where(RenderAttempt.job_id==task.id,RenderAttempt.status=='running')
            .values(status='cancelled',finished_at=utcnow()))
    db.flush();result=state(db,parent);response.headers.update(PRIVATE);db.commit();return result


def publish(job,transcript,wall_seconds,*,audio_timing=None,scene_analysis=None):
    from .project_analysis import import_transcript
    with SessionLocal.begin() as db:
        lock_owner(db,job['user_id'],allow_deleted=True)
        now=utcnow()
        child=db.scalar(select(RenderJob).where(RenderJob.id==job['id'],RenderJob.status=='processing',
            RenderJob.claim_token==job['claim_token'],RenderJob.lease_expires_at>now,RenderJob.claim_deadline_at>now))
        if not child:return False
        parent=owned_project(db,job['user_id'],job['preview_parent_id'])
        require_enabled(job['user_id'])
        if db.get(ProjectAnalysis,parent.id) is None:import_transcript(db,owner=parent.user_id,job_id=parent.id,transcript=transcript,audio_timing=audio_timing,scene_analysis=scene_analysis)
        child.status='succeeded';child.output_path=None;child.output_duration_seconds=None;child.finished_at=now
        child.lease_expires_at=None;child.claim_deadline_at=None;child.next_attempt_at=None
        db.execute(update(RenderAttempt).where(RenderAttempt.id==job['claim_token'],RenderAttempt.status=='running')
            .values(status='succeeded',finished_at=now,wall_seconds=wall_seconds,output_bytes=0))
        return True
