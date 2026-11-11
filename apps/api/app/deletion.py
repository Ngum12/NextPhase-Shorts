"""Owner-only project tombstones and bounded retryable private-volume cleanup."""
from datetime import timedelta, timezone
import logging
import shutil
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.orm import Session
from .auth import current_user
from .config import get_settings
from .db import SessionLocal, engine, session_dep
from .models import ProjectAnalysis, RenderAttempt, RenderJob, UploadPart, UploadSession, User, utcnow
from .queue import lock_owner

router=APIRouter(tags=['projects'])
logger=logging.getLogger('nextphase.deletion')


@router.delete('/api/v1/jobs/{job_id}',status_code=202)
def delete_project(job_id:str,user:User=Depends(current_user),db:Session=Depends(session_dep)):
    lock_owner(db,user.id)
    job=db.scalar(select(RenderJob).where(RenderJob.id==job_id,RenderJob.user_id==user.id).with_for_update())
    if job is None:raise HTTPException(404,'Project not found')
    descendants=list(db.scalars(select(RenderJob).where(RenderJob.preview_parent_id==job_id,
        RenderJob.user_id==user.id).order_by(RenderJob.id)))
    jobs=[job,*descendants]
    ids=[item.id for item in jobs]
    attempt=db.scalar(select(func.max(RenderAttempt.deadline_at)).where(RenderAttempt.job_id.in_(ids),
        RenderAttempt.status.in_(('running','lease_lost','cancelled'))))
    deadlines=[value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        for value in [attempt,*[v for item in jobs for v in (item.lease_expires_at,item.claim_deadline_at)]] if value]
    expiry=max(deadlines) if deadlines else None
    now=utcnow()
    after=max(now,expiry+timedelta(seconds=30)) if expiry else now
    for job in jobs:
      db.execute(delete(ProjectAnalysis).where(ProjectAnalysis.job_id==job.id))
      if job.status!='deleted':
        from .restore_journal import record
        record('project_delete',user.id,project=job.id,backend=job.media_backend,namespace=job.object_store_id)
        # Short renewable leases are not writer-lifetime bounds. Preserve the
        # hard deadlines of cancelled/lost attempts before revoking their tokens.
        job.cleanup_after=after
        job.status='deleted';job.deleted_at=now;job.finished_at=now
        job.claim_token=None;job.lease_expires_at=None;job.error_code=None
        job.title='Deleted project';job.source_path='';job.output_path=None
        job.output_duration_seconds=None
        job.preview_spec_json=None
        db.execute(update(RenderAttempt).where(RenderAttempt.job_id==job.id,
            RenderAttempt.status=='running').values(status='cancelled',finished_at=now))
        db.execute(update(UploadSession).where(UploadSession.job_id==job.id,
            UploadSession.user_id==user.id).values(status='deleted',title='Deleted project',
                file_name='deleted.mp4',source_sha256=None,parts_cleaned=False))
    db.commit()
    # Acceptance is durable before returning. Media removal is never claimed here.
    return {'status':'deleted','media_cleanup':'scheduled'}


def remove_private_tree(owner_id,leaf_id,*,staging=False):
    # Derive only canonical server UUID paths. Never follow source_path/output_path.
    if any(str(uuid.UUID(value))!=value for value in (owner_id,leaf_id)):
        raise ValueError('Noncanonical media identity')
    root=get_settings().storage_dir
    parent=root/owner_id
    for component in ([parent,parent/'.uploads'] if staging else [parent]):
        if component.is_symlink() or getattr(component,'is_junction',lambda:False)():
            raise ValueError('Unsafe media parent')
    target=parent/'.uploads'/leaf_id if staging else parent/leaf_id
    try:
        if target.is_symlink() or getattr(target,'is_junction',lambda:False)():
            target.unlink() if target.is_symlink() else target.rmdir()
        else:shutil.rmtree(target)
    except FileNotFoundError:pass


def cleanup_deleted(limit=100):
    if not 1<=limit<=1000:raise ValueError('Cleanup limit must be 1–1000')
    with SessionLocal() as db:
        rows=list(db.execute(select(RenderJob.id,RenderJob.user_id,RenderJob.media_backend,RenderJob.object_store_id).where(
            RenderJob.status=='deleted',RenderJob.cleanup_after<=utcnow())
            .order_by(case((RenderJob.media_deleted_at.is_(None),0),else_=1),
                func.coalesce(RenderJob.cleanup_attempted_at,RenderJob.deleted_at),RenderJob.id).limit(limit)))
    cleaned=0
    for job_id,owner_id,backend,store_id in rows:
        success=False
        try:
            if backend == 's3':
                from .object_store import remove_project, namespace_id
                if store_id != namespace_id():
                    raise ValueError('Stored private namespace differs from current configuration')
                remove_project(owner_id, job_id)
            remove_private_tree(owner_id,job_id)
            with SessionLocal() as db:
                sessions=list(db.scalars(select(UploadSession.id).where(UploadSession.job_id==job_id,
                    UploadSession.user_id==owner_id)))
            for session_id in sessions:
                remove_private_tree(owner_id,session_id,staging=True)
                from .uploads import cleanup_parts
                if not cleanup_parts(owner_id, session_id):
                    raise RuntimeError('Upload staging removal deferred')
            success=True
        except (OSError,ValueError,RuntimeError):
            logger.warning('project media cleanup deferred')  # No customer paths.
        with SessionLocal.begin() as db:
            db.execute(update(RenderJob).where(RenderJob.id==job_id,RenderJob.status=='deleted')
                .values(cleanup_attempted_at=utcnow(),media_deleted_at=utcnow() if success else None))
            if success:
                ids=select(UploadSession.id).where(UploadSession.job_id==job_id,UploadSession.user_id==owner_id)
                db.execute(delete(UploadPart).where(UploadPart.session_id.in_(ids)))
                db.execute(update(UploadSession).where(UploadSession.id.in_(ids)).values(parts_cleaned=True))
        cleaned+=int(success)
    return cleaned


if __name__=='__main__':
    from .migrate import require_current_schema
    require_current_schema(engine)
    print(f'Cleaned {cleanup_deleted()} deleted project media trees.')
