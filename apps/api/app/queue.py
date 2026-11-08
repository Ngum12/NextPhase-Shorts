"""Short owner-row transactions serialize admission and worker capacity checks."""
from fastapi import HTTPException
from sqlalchemy import func, select, update
from .models import RenderJob, UploadSession, User, QueueSignal, DeadLetter, utcnow
from .config import get_settings
from .storage import require_capacity

ACTIVE_STATUSES = ('queued', 'processing')


def lock_owner(db, user_id, *, allow_deleted=False):
    # SQLite has no FOR UPDATE. A no-op UPDATE acquires its write lock; PostgreSQL
    # acquires the owner row lock. Never hold this across upload or render I/O.
    query=update(User).where(User.id==user_id)
    if not allow_deleted:query=query.where(User.deleted_at.is_(None))
    result=db.execute(query.values(id=User.id),
               execution_options={'synchronize_session': False})
    if result.rowcount!=1:raise HTTPException(401,'Account is unavailable. Sign in again.')


def active_count(db, user_id):
    return db.scalar(select(func.count()).select_from(RenderJob).where(
        RenderJob.user_id == user_id, RenderJob.status.in_(ACTIVE_STATUSES)))


def reserved_upload_count(db, user_id, exclude=None):
    query = select(func.count()).select_from(UploadSession).where(
        UploadSession.user_id == user_id, UploadSession.status == 'uploading',
        UploadSession.expires_at > utcnow())
    if exclude:
        query = query.where(UploadSession.id != exclude)
    return db.scalar(query)


def admit_job(db, job, *, upload_session_id=None,source_bytes=None):
    """Returns (job, replayed); caller commits. Fingerprint includes source bytes."""
    lock_owner(db, job.user_id)
    if job.idempotency_key:
        existing = db.scalar(select(RenderJob).where(RenderJob.user_id == job.user_id,
                             RenderJob.idempotency_key == job.idempotency_key))
        if existing:
            if existing.status == 'deleted':
                raise HTTPException(410, 'This project was deleted. Start a new upload with a new key.')
            if existing.request_hash != job.request_hash:
                raise HTTPException(409, 'This upload key was already used for a different video or settings')
            from .observability import bind_job
            bind_job(existing)
            return existing, True
    reservation = None
    if upload_session_id:
        reservation = db.scalar(select(UploadSession.id).where(
            UploadSession.id == upload_session_id, UploadSession.user_id == job.user_id,
            UploadSession.status == 'uploading', UploadSession.expires_at > utcnow()))
        if reservation is None:
            raise HTTPException(409, 'Upload reservation is no longer active')
    # An existing reservation already owns its slot. Converting it must remain
    # possible even if an administrator lowered the limit while it was paused.
    if reservation is None and active_count(db, job.user_id) + reserved_upload_count(db, job.user_id) >= get_settings().max_active_jobs_per_user:
        raise HTTPException(429, 'Your queue is full. Wait for a job to finish or cancel one.',
                            headers={'Retry-After': '5'})
    if job.storage_reserved_bytes is None or job.max_render_bytes is None:
        raise ValueError('Admission requires a server storage reservation')
    if reservation is None:
        require_capacity(db,job.user_id,job.storage_reserved_bytes)
    from .observability import bind_job
    bind_job(job)
    db.add(job)
    db.flush()
    if source_bytes is not None:
        from .costs import measure_artifact
        measure_artifact(job.id,'original',source_bytes,db=db)
    if get_settings().queue_backend=='valkey':
        import uuid
        now=utcnow()
        db.add(QueueSignal(job_id=job.id,generation=str(uuid.uuid4()),created_at=now,next_publish_at=now))
    return job, False


def dead_letter(db,job_id,reason,attempts):
    from .db import engine
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert=pg_insert if engine.dialect.name=='postgresql' else sqlite_insert
    db.execute(insert(DeadLetter).values(job_id=job_id,reason=reason,attempts=attempts,created_at=utcnow())
        .on_conflict_do_nothing(index_elements=['job_id']))
