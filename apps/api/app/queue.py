"""Short owner-row transactions serialize admission and worker capacity checks."""
from fastapi import HTTPException
from sqlalchemy import func, select, update
from .models import RenderJob, User
from .config import get_settings

ACTIVE_STATUSES = ('queued', 'processing')


def lock_owner(db, user_id):
    # SQLite has no FOR UPDATE. A no-op UPDATE acquires its write lock; PostgreSQL
    # acquires the owner row lock. Never hold this across upload or render I/O.
    db.execute(update(User).where(User.id == user_id).values(id=User.id),
               execution_options={'synchronize_session': False})


def active_count(db, user_id):
    return db.scalar(select(func.count()).select_from(RenderJob).where(
        RenderJob.user_id == user_id, RenderJob.status.in_(ACTIVE_STATUSES)))


def admit_job(db, job):
    """Returns (job, replayed); caller commits. Fingerprint includes source bytes."""
    lock_owner(db, job.user_id)
    if job.idempotency_key:
        existing = db.scalar(select(RenderJob).where(RenderJob.user_id == job.user_id,
                             RenderJob.idempotency_key == job.idempotency_key))
        if existing:
            if existing.request_hash != job.request_hash:
                raise HTTPException(409, 'This upload key was already used for a different video or settings')
            return existing, True
    if active_count(db, job.user_id) >= get_settings().max_active_jobs_per_user:
        raise HTTPException(429, 'Your queue is full. Wait for a job to finish or cancel one.',
                            headers={'Retry-After': '5'})
    db.add(job)
    db.flush()
    return job, False
