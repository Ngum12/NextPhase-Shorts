"""DB-backed queue with bounded leases and fenced, attempt-specific artifacts.

Development can poll the DB; Valkey/Arq dispatch shares the same fenced scheduler.
"""
import logging
import json
import signal
import time
import uuid
from datetime import timedelta
from pathlib import Path
from sqlalchemy import func, select, update,or_
from sqlalchemy.exc import SQLAlchemyError
from .config import get_settings
from .db import SessionLocal, engine
from .migrate import require_current_schema
from .media import MediaCancelled, MediaError, OutputLimitExceeded, RenderDeadlineExceeded, render_baseline
from .asr_failures import AsrFailure
from .documentary_plan import DocumentaryFailure
from .models import RenderAttempt, RenderJob, User, utcnow
from .queue import lock_owner,dead_letter
from . import object_store
from .analysis_limits import ANALYSIS_OVERHEAD_SECONDS

logging.basicConfig(level=logging.INFO, format="%(message)s")
from .worker_events import emit
from .worker_health import WorkerHeartbeat
stop = False
settings = get_settings()
from .storage import MAX_RENDER_ATTEMPTS
MAX_ATTEMPTS = MAX_RENDER_ATTEMPTS


def request_stop(*_):
    global stop
    stop = True


def claim_job():
    with SessionLocal.begin() as db:
        due=or_(RenderJob.next_attempt_at.is_(None),RenderJob.next_attempt_at<=utcnow())
        queued = select(func.min(RenderJob.created_at)).where(
            RenderJob.user_id == User.id, RenderJob.status == 'queued',due,
            RenderJob.attempt_count < MAX_ATTEMPTS).correlate(User).scalar_subquery()
        running = select(func.count()).where(RenderJob.user_id == User.id,
            RenderJob.status == 'processing').correlate(User).scalar_subquery()
        last_claim = select(func.max(RenderAttempt.started_at)).join(RenderJob,
            RenderAttempt.job_id == RenderJob.id).where(RenderJob.user_id == User.id).correlate(User).scalar_subquery()
        owner_query = select(User.id).where(queued.is_not(None),
            User.deleted_at.is_(None),
            running < settings.max_processing_jobs_per_user).order_by(last_claim.asc().nullsfirst(), queued, User.id).limit(1)
        if engine.dialect.name == 'postgresql':
            owner_query = owner_query.with_for_update(skip_locked=True)
        owner_id = db.scalar(owner_query)
        if owner_id is None:
            return None
        lock_owner(db, owner_id, allow_deleted=True)
        if db.get(User, owner_id).deleted_at is not None:
            return None
        # Recheck after acquiring the lock: another claimant may have won first.
        count = db.scalar(select(func.count()).select_from(RenderJob).where(
            RenderJob.user_id == owner_id, RenderJob.status == 'processing'))
        if count >= settings.max_processing_jobs_per_user:
            return None
        job_id = db.scalar(select(RenderJob.id).where(RenderJob.user_id == owner_id,
            RenderJob.status == 'queued',due, RenderJob.attempt_count < MAX_ATTEMPTS)
            .order_by(RenderJob.created_at, RenderJob.id).limit(1))
        if job_id is None:
            return None
        from .capacity import worker_available
        if not worker_available(db):return None
        now = utcnow()
        token = str(uuid.uuid4())
        selected=db.get(RenderJob,job_id)
        budget=(settings.english_analysis_timeout_seconds+ANALYSIS_OVERHEAD_SECONDS if selected.operation=='analysis'
                else settings.render_timeout_seconds+(300 if selected.media_backend=='s3' else 90))
        # Compare-and-set also protects SQLite, which has no SKIP LOCKED.
        job = db.execute(update(RenderJob).where(
            RenderJob.id == job_id, RenderJob.status == 'queued',
            RenderJob.attempt_count < MAX_ATTEMPTS).values(
                status='processing', attempt_count=RenderJob.attempt_count + 1,
                started_at=now, finished_at=None, error_code=None,
                output_path=None, output_duration_seconds=None, claim_token=token,
                next_attempt_at=None,lease_expires_at=now+timedelta(seconds=min(settings.worker_lease_seconds,budget)),
                claim_deadline_at=now+timedelta(seconds=budget))
            .returning(RenderJob)).scalar_one_or_none()
        if job is None:
            return None
        db.add(RenderAttempt(id=token,job_id=job.id,number=job.attempt_count,started_at=now,status='running',deadline_at=job.claim_deadline_at))
        return {'trace_id':job.trace_id,'parent_span_id':job.parent_span_id,'id': job.id, 'user_id': job.user_id, 'source': job.source_path,
                'desired_seconds': job.desired_seconds, 'source_duration': job.source_duration_seconds,
                'claim_token': token, 'media_backend': job.media_backend,
                'object_store_id': job.object_store_id,
                'max_render_bytes': job.max_render_bytes or settings.max_render_bytes,
                'preview_parent_id':job.preview_parent_id,'preview_spec_json':job.preview_spec_json,'operation':job.operation}


def mark_done(job_id: str, claim_token: str, *, output_path=None, output_duration=None, error_code=None, wall_seconds=None, output_bytes=None,retryable=False):
    now = utcnow()
    values = dict(finished_at=now, lease_expires_at=None,claim_deadline_at=None,next_attempt_at=None,
                  status='failed' if error_code else 'succeeded', error_code=error_code,
                  output_path=None if error_code else str(output_path),
                  output_duration_seconds=None if error_code else output_duration)
    with SessionLocal.begin() as db:
        job=db.get(RenderJob,job_id)
        requeue=bool(error_code and retryable and job and job.attempt_count<MAX_ATTEMPTS)
        if requeue:
            values.update(status='queued',finished_at=None,started_at=None,error_code=None,claim_token=None,
                next_attempt_at=now+timedelta(seconds=settings.retry_backoff_seconds*2**max(0,job.attempt_count-1)))
        result = db.execute(update(RenderJob).where(
            RenderJob.id == job_id, RenderJob.status == 'processing',
            RenderJob.claim_token == claim_token, RenderJob.lease_expires_at > now,
            or_(RenderJob.claim_deadline_at.is_(None),RenderJob.claim_deadline_at>now)).values(**values),
            execution_options={'synchronize_session':False})
        if result.rowcount == 1:
            db.execute(update(RenderAttempt).where(RenderAttempt.id == claim_token,
                RenderAttempt.status == 'running').values(status='failed' if error_code else 'succeeded',finished_at=now,
                    wall_seconds=wall_seconds,output_bytes=None if error_code else output_bytes))
            if error_code and not requeue:dead_letter(db,job_id,error_code,job.attempt_count)
        return result.rowcount == 1


def owns_claim(job):
    with SessionLocal() as db:
        return db.scalar(select(RenderJob.id).where(
            RenderJob.id == job['id'], RenderJob.status == 'processing',
            RenderJob.claim_token == job['claim_token'], RenderJob.lease_expires_at > utcnow(),
            or_(RenderJob.claim_deadline_at.is_(None),RenderJob.claim_deadline_at>utcnow()))) is not None


def process(job):
    from .job_supervision import ClaimSupervisor
    from .observability import Recorder,current,stage,save
    recorder=Recorder(trace_id=job.get('trace_id') or job['id'].replace('-',''),
        parent_id=job.get('parent_span_id'),job_id=job['id'],attempt_id=job['claim_token'])
    context=current.set(recorder)
    try:
        with stage('attempt'):
            with ClaimSupervisor(job) as supervisor:
                _process(job,supervisor)
    finally:
        current.reset(context)
        # The process handles media errors internally; root span follows durable attempt state.
        try:
            with SessionLocal() as db:
                state=db.get(RenderAttempt,job['claim_token'])
                for row in recorder.rows:
                    if row['stage']=='attempt' and (state is None or state.status!='succeeded'):row['outcome']='error'
        except SQLAlchemyError:
            from .observability import logger
            logger.warning('observation_state_unavailable')
            for row in recorder.rows:
                if row['stage']=='attempt':row['outcome']='error'
        save(recorder)


def _process(job,supervisor):
    from .observability import stage
    token = job['claim_token']
    output = settings.storage_dir / job['user_id'] / job['id'] / token / 'output.mp4'
    began = time.monotonic()
    source = Path(job['source'])
    remote = job.get('media_backend', 'local') == 's3'
    excerpt = bool(job.get('preview_parent_id'))
    if remote or excerpt:
        source = output.parent / 'input.media'
    try:
        if stop or supervisor.lost.is_set():
            raise MediaCancelled('Worker stopping')
        if remote:
            object_store.require_namespace(job.get('object_store_id'))
            output.parent.mkdir(parents=True, exist_ok=True)
            extension = Path(job['source'].split('#', 1)[0]).suffix
            from .observability import stage
            with stage('source_fetch') as observed:
                object_store.fetch(job['source'], object_store.source_key(job['user_id'], job['id'], extension),
                                   source, settings.max_upload_bytes)
                observed['storage_read_bytes']=source.stat().st_size
        cancelled=lambda: stop or supervisor.lost.is_set() or not owns_claim(job)
        if job.get('operation')=='analysis':
            from .analysis_work import process_analysis
            if remote:raise MediaError('Analysis requires a local source')
            if process_analysis(job,source,should_cancel=cancelled):emit('analysis_completed',job_id=job['id'])
            return
        documentary=excerpt and json.loads(job['preview_spec_json']).get('schema_version')=='documentary-job-1'
        if documentary:
            if remote:raise MediaError('Unsupported documentary source profile')
            from .documentary_work import process_documentary
            info=process_documentary(job,source,output,should_cancel=cancelled)
        elif excerpt:
            if remote:raise MediaError('Unsupported preview source profile')
            from .excerpt_jobs import snapshot_source
            from .excerpt_render import render_excerpt
            with stage('source_fetch') as observed:
                spec=snapshot_source(job,source,should_cancel=cancelled)
                observed['storage_read_bytes']=spec.source_bytes
                observed['storage_write_bytes']=spec.source_bytes
            info=render_excerpt(source,output,start_ms=spec.source_start_ms,end_ms=spec.source_end_ms,
                frames=spec.output_frames,requested_seconds=spec.requested_seconds,
                captions=spec.captions,
                framing=spec.framing,
                polish=spec.polish,
                max_output_bytes=job.get('max_render_bytes',settings.max_render_bytes),
                should_cancel=cancelled,timeout=min(300,settings.render_timeout_seconds))
        else:
            duration = max(1, min(60, job['desired_seconds'], int(job['source_duration'] + 0.5)))
            info = render_baseline(source, output, duration, max_output_bytes=job.get('max_render_bytes',settings.max_render_bytes), should_cancel=cancelled)
        output_bytes = output.stat().st_size
        output_reference = output.resolve()
        if remote:
            if stop or not owns_claim(job):
                raise MediaCancelled('Claim lost before private upload')
            from .observability import stage
            with stage('output_publish') as observed:
                output_reference = object_store.put(output, object_store.output_key(job['user_id'], job['id'], token),
                                                    job.get('max_render_bytes', settings.max_render_bytes))
                observed['storage_write_bytes']=output_bytes
        if mark_done(job['id'], token, output_path=output_reference, output_duration=info['duration'],
                     wall_seconds=time.monotonic()-began, output_bytes=output_bytes):
            from .costs import measure_artifact
            measure_artifact(job['id'],'output',output_bytes)
            emit('render_completed',job_id=job['id'],output_seconds=info['duration'])
        else:
            # A recovered attempt can never replace or remove the winner's artifact.
            output.unlink(missing_ok=True)
            emit('render_stale',job_id=job['id'])
    except MediaCancelled:
        emit('render_cancelled',job_id=job['id'])
    except OutputLimitExceeded:
        emit('output_limit_exceeded',job_id=job['id'])
        mark_done(job['id'], token, error_code='OUTPUT_LIMIT_EXCEEDED', wall_seconds=time.monotonic()-began)
    except AsrFailure as failure:
        # Only fixed, non-content diagnostic codes leave the protected worker.
        emit('render_failed',job_id=job['id'])
        mark_done(job['id'], token, error_code=failure.code, wall_seconds=time.monotonic()-began)
    except DocumentaryFailure as failure:
        emit('render_failed',job_id=job['id'])
        code='RENDER_DEADLINE_EXCEEDED' if failure.code=='DEADLINE_EXCEEDED' else 'DOCUMENTARY_'+failure.code
        mark_done(job['id'],token,error_code=code,wall_seconds=time.monotonic()-began)
    except RenderDeadlineExceeded:
        emit('render_failed',job_id=job['id'])
        mark_done(job['id'], token, error_code='RENDER_DEADLINE_EXCEEDED', wall_seconds=time.monotonic()-began)
    except MediaError:
        emit('render_failed',job_id=job['id'])
        mark_done(job['id'], token, error_code='ANALYSIS_FAILED' if job.get('operation')=='analysis' else 'RENDER_FAILED', wall_seconds=time.monotonic()-began)
    except object_store.ObjectStoreError:
        emit('storage_unavailable',job_id=job['id'])
        mark_done(job['id'], token, error_code='STORAGE_UNAVAILABLE', wall_seconds=time.monotonic()-began,retryable=True)
    except Exception:
        # Do not log raw exception messages/tracebacks containing customer paths.
        emit('render_internal_error',job_id=job['id'])
        mark_done(job['id'], token, error_code='INTERNAL_ERROR', wall_seconds=time.monotonic()-began,retryable=True)

    finally:
        if stop:
            # Make this claim eligible for bounded recovery only after render
            # teardown. A signal cannot revoke a newer attempt or terminal job.
            with SessionLocal.begin() as db:
                db.execute(update(RenderJob).where(RenderJob.id==job['id'],
                    RenderJob.status=='processing',RenderJob.claim_token==token)
                    .values(lease_expires_at=utcnow()))
        if remote or excerpt:
            source.unlink(missing_ok=True)
        if remote:
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


def recover_stale_jobs(limit=100):
    if not 1 <= limit <= 1000:
        raise ValueError('Recovery batch must be 1–1000')
    from .automatic_analysis import reconcile_requested
    reconcile_requested(min(limit,10))
    now = utcnow()
    expired = (RenderJob.status == 'processing', or_(RenderJob.lease_expires_at.is_(None),
        RenderJob.lease_expires_at <= now,RenderJob.claim_deadline_at<=now))
    with SessionLocal.begin() as db:
        # Lock expired jobs before recording loss, so completion cannot win between
        # the attempt record and recovery. SQLite's first write serializes writers.
        candidates=select(RenderJob.id).where(*expired).order_by(RenderJob.lease_expires_at,RenderJob.id).limit(limit)
        if engine.dialect.name == 'postgresql':
            candidates=candidates.with_for_update(skip_locked=True)
        ids=list(db.scalars(candidates))
        if not ids:return (0,0)
        expired=(*expired,RenderJob.id.in_(ids))
        db.execute(update(RenderAttempt).where(RenderAttempt.status == 'running',
            RenderAttempt.id.in_(select(RenderJob.claim_token).where(*expired)))
            .values(status='lease_lost',finished_at=now))
        # Atomic updates, rather than loading rows which can change before commit.
        failed = db.execute(update(RenderJob).where(*expired,
            RenderJob.attempt_count >= MAX_ATTEMPTS).values(
                status='failed', error_code='MAX_RETRIES', finished_at=now,
                claim_token=None, lease_expires_at=None,claim_deadline_at=None,next_attempt_at=None))
        requeued = db.execute(update(RenderJob).where(*expired,
            RenderJob.attempt_count < MAX_ATTEMPTS).values(
                status='queued', started_at=None, error_code=None,
                claim_token=None, lease_expires_at=None,claim_deadline_at=None,next_attempt_at=None))
        for identity in ids:
            job=db.get(RenderJob,identity)
            if job.status=='failed':dead_letter(db,identity,'MAX_RETRIES',job.attempt_count)
        return requeued.rowcount, failed.rowcount


def main():
    if settings.env in ('staging','production') and (settings.queue_backend!='valkey' or
            not settings.worker_require_limits or not settings.worker_require_sandbox):
        raise RuntimeError('Production workers require durable broker and enforced resource/filesystem/network guards')
    if settings.queue_backend=='valkey':
        from .broker_worker import main as broker_main
        broker_main();return
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    if settings.worker_require_limits:
        from .worker_limits import require_worker_limits,require_unprivileged
        require_unprivileged();require_worker_limits()
    if settings.worker_require_sandbox:
        from .render_sandbox import require_support
        require_support()
    require_current_schema(engine)
    if settings.media_backend == 's3':
        object_store.check_bucket()
    with WorkerHeartbeat(settings.worker_heartbeat_seconds) as heartbeat:
        last_upload_cleanup = 0.0
        while not stop:
            try:
                if time.monotonic() - last_upload_cleanup >= 60:
                    heartbeat.phase('maintenance')
                    from .upload_cleanup import cleanup_uploads
                    cleanup_uploads()
                    from .auth_limits import cleanup_auth
                    cleanup_auth()
                    from .deletion import cleanup_deleted
                    cleanup_deleted()
                    from .account_deletion import cleanup_accounts
                    cleanup_accounts()
                    from .metadata_cleanup import cleanup
                    cleanup()
                    last_upload_cleanup = time.monotonic()
                requeued,failed=recover_stale_jobs()
                if requeued or failed:emit('lease_recovery',worker_id=heartbeat.id,requeued=requeued,failed=failed)
                if stop:break
                heartbeat.phase('idle')
                job = claim_job()
                if job:
                    heartbeat.phase('rendering')
                    process(job)
                else:
                    time.sleep(settings.worker_poll_seconds)
            except SQLAlchemyError:
                # A failed DB round-trip cannot be acknowledged as completion. The
                # durable lease and existing retry cap remain the source of truth.
                heartbeat.phase('database_retry')
                emit('database_unavailable',worker_id=heartbeat.id)
                time.sleep(settings.worker_poll_seconds)


if __name__ == '__main__':
    main()
