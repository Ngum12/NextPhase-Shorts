"""Single-job worker for Phase 1. PostgreSQL SKIP LOCKED coordinates workers.

Future: dedicated queue, backpressure, region routing, quotas, cancellation and retries.
"""
import logging
import signal
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select, update
from .config import get_settings
from .db import Base, SessionLocal, engine
from .media import MediaError, render_baseline
from .models import RenderJob, utcnow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("nextphase.worker")
stop = False
settings = get_settings()

def request_stop(*_):
    global stop
    stop = True

def claim_job():
    with SessionLocal.begin() as db:
        statement = select(RenderJob).where(RenderJob.status == "queued").order_by(RenderJob.created_at.asc())
        if engine.dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        job = db.scalars(statement.limit(1)).first()
        if job is None:
            return None
        job.status = "processing"
        job.attempt_count += 1
        job.started_at = utcnow()
        return {"id": job.id, "user_id": job.user_id, "source": job.source_path,
                "desired_seconds": job.desired_seconds, "source_duration": job.source_duration_seconds}

def mark_done(job_id: str, *, output_path=None, output_duration=None, error_code=None):
    with SessionLocal.begin() as db:
        job = db.get(RenderJob, job_id)
        if not job:
            return
        job.finished_at = utcnow()
        if error_code:
            job.status = "failed"
            job.error_code = error_code
        else:
            job.status = "succeeded"
            job.output_path = str(output_path)
            job.output_duration_seconds = output_duration

def process(job):
    job_id = job["id"]
    output = settings.storage_dir / job["user_id"] / job_id / "output.mp4"
    try:
        duration = max(1, min(60, job["desired_seconds"], int(job["source_duration"] + 0.5)))
        info = render_baseline(Path(job["source"]), output, duration)
        mark_done(job_id, output_path=output.resolve(), output_duration=info["duration"])
        logger.info("render completed job_id=%s seconds=%.2f", job_id, info["duration"])
    except MediaError:
        logger.exception("media error job_id=%s", job_id)
        mark_done(job_id, error_code="RENDER_FAILED")
    except Exception:
        logger.exception("unexpected error job_id=%s", job_id)
        mark_done(job_id, error_code="INTERNAL_ERROR")

def recover_stale_jobs():
    # A crashed worker should not leave jobs in processing forever. Maximum 2 attempts.
    cutoff = utcnow() - timedelta(seconds=settings.render_timeout_seconds + 90)
    with SessionLocal.begin() as db:
        stale = db.scalars(select(RenderJob).where(RenderJob.status == "processing",
                             RenderJob.started_at < cutoff)).all()
        for job in stale:
            if job.attempt_count >= 2:
                job.status = "failed"
                job.error_code = "MAX_RETRIES"
                job.finished_at = utcnow()
            else:
                job.status = "queued"
                job.started_at = None
                job.error_code = None

def main():
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    Base.metadata.create_all(bind=engine)
    logger.info("NextPhase worker started (baseline FFmpeg, no AI)")
    while not stop:
        recover_stale_jobs()
        job = claim_job()
        if job:
            process(job)
        else:
            time.sleep(settings.worker_poll_seconds)

if __name__ == "__main__":
    main()
