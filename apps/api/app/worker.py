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
from .media import MediaCancelled, MediaError, OutputLimitExceeded, render_baseline
from .models import RenderAttempt, RenderJob, User, utcnow
from .queue import lock_owner
from . import object_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("nextphase.worker")
stop = False
settings = get_settings()
from .storage import MAX_RENDER_ATTEMPTS
MAX_ATTEMPTS = MAX_RENDER_ATTEMPTS


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
                lease_expires_at=now + timedelta(seconds=settings.render_timeout_seconds +
                    (300 if db.get(RenderJob, job_id).media_backend == 's3' else 90)))
            .returning(RenderJob)).scalar_one_or_none()
        if job is None:
            return None
        db.add(RenderAttempt(id=token,job_id=job.id,number=job.attempt_count,started_at=now,status='running'))
        return {'id': job.id, 'user_id': job.user_id, 'source': job.source_path,
                'desired_seconds': job.desired_seconds, 'source_duration': job.source_duration_seconds,
                'claim_token': token, 'media_backend': job.media_backend,
                'object_store_id': job.object_store_id,
                'max_render_bytes': job.max_render_bytes or settings.max_render_bytes}


def mark_done(job_id: str, claim_token: str, *, output_path=None, output_duration=None, error_code=None, wall_seconds=None, output_bytes=None):
    now = utcnow()
    values = dict(finished_at=now, lease_expires_at=None,
                  status='failed' if error_code else 'succeeded', error_code=error_code,
                  output_path=None if error_code else str(output_path),
                  output_duration_seconds=None if error_code else output_duration)
    with SessionLocal.begin() as db:
        result = db.execute(update(RenderJob).where(
            RenderJob.id == job_id, RenderJob.status == 'processing',
            RenderJob.claim_token == claim_token, RenderJob.lease_expires_at > now).values(**values))
        if result.rowcount == 1:
            db.execute(update(RenderAttempt).where(RenderAttempt.id == claim_token,
                RenderAttempt.status == 'running').values(status=values['status'],finished_at=now,
                    wall_seconds=wall_seconds,output_bytes=None if error_code else output_bytes))
        return result.rowcount == 1


def owns_claim(job):
    with SessionLocal() as db:
        return db.scalar(select(RenderJob.id).where(
            RenderJob.id == job['id'], RenderJob.status == 'processing',
            RenderJob.claim_token == job['claim_token'], RenderJob.lease_expires_at > utcnow())) is not None


def process(job):
    token = job['claim_token']
    output = settings.storage_dir / job['user_id'] / job['id'] / token / 'output.mp4'
    began = time.monotonic()
    source = Path(job['source'])
    remote = job.get('media_backend', 'local') == 's3'
    if remote:
        source = output.parent / 'input.media'
    try:
        if remote:
            object_store.require_namespace(job.get('object_store_id'))
            output.parent.mkdir(parents=True, exist_ok=True)
            extension = Path(job['source'].split('#', 1)[0]).suffix
            object_store.fetch(job['source'], object_store.source_key(job['user_id'], job['id'], extension),
                               source, settings.max_upload_bytes)
        duration = max(1, min(60, job['desired_seconds'], int(job['source_duration'] + 0.5)))
        info = render_baseline(source, output, duration, max_output_bytes=job.get('max_render_bytes',settings.max_render_bytes), should_cancel=lambda: not owns_claim(job))
        output_bytes = output.stat().st_size
        output_reference = output.resolve()
        if remote:
            if not owns_claim(job):
                raise MediaCancelled('Claim lost before private upload')
            output_reference = object_store.put(output, object_store.output_key(job['user_id'], job['id'], token),
                                                job.get('max_render_bytes', settings.max_render_bytes))
        if mark_done(job['id'], token, output_path=output_reference, output_duration=info['duration'],
                     wall_seconds=time.monotonic()-began, output_bytes=output_bytes):
            logger.info('render completed job_id=%s seconds=%.2f', job['id'], info['duration'])
        else:
            # A recovered attempt can never replace or remove the winner's artifact.
            output.unlink(missing_ok=True)
            logger.warning('discarded stale render job_id=%s', job['id'])
    except MediaCancelled:
        logger.info('render cancelled or lease lost job_id=%s', job['id'])
    except OutputLimitExceeded:
        mark_done(job['id'], token, error_code='OUTPUT_LIMIT_EXCEEDED', wall_seconds=time.monotonic()-began)
    except MediaError:
        logger.warning('media error job_id=%s', job['id'])
        mark_done(job['id'], token, error_code='RENDER_FAILED', wall_seconds=time.monotonic()-began)
    except object_store.ObjectStoreError:
        logger.warning('private storage error job_id=%s', job['id'])
        mark_done(job['id'], token, error_code='STORAGE_UNAVAILABLE', wall_seconds=time.monotonic()-began)
    except Exception:
        # Do not log raw exception messages/tracebacks containing customer paths.
        logger.error('unexpected error job_id=%s', job['id'])
        mark_done(job['id'], token, error_code='INTERNAL_ERROR', wall_seconds=time.monotonic()-began)

    finally:
        if remote:
            source.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
        # If publication lost its fence, only close this attempt's telemetry.
        # Recovery may already have marked it lost: never overwrite that history.
        with SessionLocal.begin() as db:
            state = db.scalar(select(RenderJob.status).where(RenderJob.id == job['id']))
            db.execute(update(RenderAttempt).where(RenderAttempt.id == token,
                RenderAttempt.status.in_(['running','cancelled']),
                RenderAttempt.wall_seconds.is_(None)).values(finished_at=utcnow(),
                    status='cancelled' if state in ('cancelled','deleted') else 'lease_lost',
                    wall_seconds=time.monotonic()-began))


def recover_stale_jobs():
    now = utcnow()
    expired = (RenderJob.status == 'processing', RenderJob.lease_expires_at <= now)
    with SessionLocal.begin() as db:
        # Lock expired jobs before recording loss, so completion cannot win between
        # the attempt record and recovery. SQLite's first write serializes writers.
        if engine.dialect.name == 'postgresql':
            db.execute(select(RenderJob.id).where(*expired).with_for_update()).all()
        db.execute(update(RenderAttempt).where(RenderAttempt.status == 'running',
            RenderAttempt.id.in_(select(RenderJob.claim_token).where(*expired)))
            .values(status='lease_lost',finished_at=now))
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
    if settings.media_backend == 's3':
        object_store.check_bucket()
    logger.info('NextPhase worker started (leased baseline FFmpeg, no AI)')
    last_upload_cleanup = 0.0
    while not stop:
        if time.monotonic() - last_upload_cleanup >= 60:
            from .upload_cleanup import cleanup_uploads
            cleanup_uploads()
            from .auth_limits import cleanup_auth
            cleanup_auth()
            from .deletion import cleanup_deleted
            cleanup_deleted()
            last_upload_cleanup = time.monotonic()
        recover_stale_jobs()
        job = claim_job()
        if job:
            process(job)
        else:
            time.sleep(settings.worker_poll_seconds)


if __name__ == '__main__':
    main()
