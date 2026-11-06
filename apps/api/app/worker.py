"""DB-backed queue with bounded leases and fenced, attempt-specific artifacts.

This remains a polling queue, not a full durable broker or exactly-once execution.
"""
import logging
import signal
import time
import uuid
from datetime import timedelta
from pathlib import Path
from sqlalchemy import func, select, update
from .config import get_settings
from .db import SessionLocal, engine
from .migrate import require_current_schema
from .media import MediaCancelled, MediaError, render_baseline
from .models import RenderJob, User, utcnow
from .queue import lock_owner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("nextphase.worker")
stop = False
settings = get_settings()
MAX_ATTEMPTS = 2


def request_stop(*_):
    global stop
    stop = True


def claim_job():
    with SessionLocal.begin() as db:
        queued = select(func.min(RenderJob.created_at)).where(
            RenderJob.user_id == User.id, RenderJob.status == 'queued',
            RenderJob.attempt_count < MAX_ATTEMPTS).correlate(User).scalar_subquery()
        running = select(func.count()).where(RenderJob.user_id == User.id,
            RenderJob.status == 'processing').correlate(User).scalar_subquery()
        owner_query = select(User.id).where(queued.is_not(None),
            running < settings.max_processing_jobs_per_user).order_by(queued, User.id).limit(1)
        if engine.dialect.name == 'postgresql':
            owner_query = owner_query.with_for_update(skip_locked=True)
        owner_id = db.scalar(owner_query)
        if owner_id is None:
            return None
        lock_owner(db, owner_id)
        # Recheck after acquiring the lock: another claimant may have won first.
        count = db.scalar(select(func.count()).select_from(RenderJob).where(
            RenderJob.user_id == owner_id, RenderJob.status == 'processing'))
        if count >= settings.max_processing_jobs_per_user:
            return None
        job_id = db.scalar(select(RenderJob.id).where(RenderJob.user_id == owner_id,
            RenderJob.status == 'queued', RenderJob.attempt_count < MAX_ATTEMPTS)
            .order_by(RenderJob.created_at, RenderJob.id).limit(1))
        if job_id is None:
            return None
        now = utcnow()
        token = str(uuid.uuid4())
        # Compare-and-set also protects SQLite, which has no SKIP LOCKED.
        job = db.execute(update(RenderJob).where(
            RenderJob.id == job_id, RenderJob.status == 'queued',
            RenderJob.attempt_count < MAX_ATTEMPTS).values(
                status='processing', attempt_count=RenderJob.attempt_count + 1,
                started_at=now, finished_at=None, error_code=None,
                output_path=None, output_duration_seconds=None, claim_token=token,
                lease_expires_at=now + timedelta(seconds=settings.render_timeout_seconds + 90))
            .returning(RenderJob)).scalar_one_or_none()
        if job is None:
            return None
        return {'id': job.id, 'user_id': job.user_id, 'source': job.source_path,
                'desired_seconds': job.desired_seconds, 'source_duration': job.source_duration_seconds,
                'claim_token': token}


def mark_done(job_id: str, claim_token: str, *, output_path=None, output_duration=None, error_code=None):
    now = utcnow()
    values = dict(finished_at=now, lease_expires_at=None,
                  status='failed' if error_code else 'succeeded', error_code=error_code,
                  output_path=None if error_code else str(output_path),
                  output_duration_seconds=None if error_code else output_duration)
    with SessionLocal.begin() as db:
        result = db.execute(update(RenderJob).where(
            RenderJob.id == job_id, RenderJob.status == 'processing',
            RenderJob.claim_token == claim_token, RenderJob.lease_expires_at > now).values(**values))
        return result.rowcount == 1


def owns_claim(job):
    with SessionLocal() as db:
        return db.scalar(select(RenderJob.id).where(
            RenderJob.id == job['id'], RenderJob.status == 'processing',
            RenderJob.claim_token == job['claim_token'], RenderJob.lease_expires_at > utcnow())) is not None


def process(job):
    token = job['claim_token']
    output = settings.storage_dir / job['user_id'] / job['id'] / token / 'output.mp4'
    try:
        duration = max(1, min(60, job['desired_seconds'], int(job['source_duration'] + 0.5)))
        info = render_baseline(Path(job['source']), output, duration, should_cancel=lambda: not owns_claim(job))
        if mark_done(job['id'], token, output_path=output.resolve(), output_duration=info['duration']):
            logger.info('render completed job_id=%s seconds=%.2f', job['id'], info['duration'])
        else:
            # A recovered attempt can never replace or remove the winner's artifact.
            output.unlink(missing_ok=True)
            logger.warning('discarded stale render job_id=%s', job['id'])
    except MediaCancelled:
        logger.info('render cancelled or lease lost job_id=%s', job['id'])
    except MediaError:
        logger.warning('media error job_id=%s', job['id'])
        mark_done(job['id'], token, error_code='RENDER_FAILED')
    except Exception:
        logger.exception('unexpected error job_id=%s', job['id'])
        mark_done(job['id'], token, error_code='INTERNAL_ERROR')


def recover_stale_jobs():
    now = utcnow()
    expired = (RenderJob.status == 'processing', RenderJob.lease_expires_at <= now)
    with SessionLocal.begin() as db:
        # Atomic updates, rather than loading rows which can change before commit.
        failed = db.execute(update(RenderJob).where(*expired,
            RenderJob.attempt_count >= MAX_ATTEMPTS).values(
                status='failed', error_code='MAX_RETRIES', finished_at=now,
                claim_token=None, lease_expires_at=None))
        requeued = db.execute(update(RenderJob).where(*expired,
            RenderJob.attempt_count < MAX_ATTEMPTS).values(
                status='queued', started_at=None, error_code=None,
                claim_token=None, lease_expires_at=None))
        return requeued.rowcount, failed.rowcount


def main():
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    require_current_schema(engine)
    logger.info('NextPhase worker started (leased baseline FFmpeg, no AI)')
    while not stop:
        recover_stale_jobs()
        job = claim_job()
        if job:
            process(job)
        else:
            time.sleep(settings.worker_poll_seconds)


if __name__ == '__main__':
    main()
