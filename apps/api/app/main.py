"""FastAPI starter. Payment access is DISABLED. No AI editing is claimed in Phase 1."""
import hashlib
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from starlette.background import BackgroundTask
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from .auth import current_user,upload_user
from .auth_routes import router as auth_router
from .auth_actions import router as auth_actions_router
from .deletion import router as deletion_router
from .config import get_settings
from .db import engine, session_dep
from .migrate import require_current_schema
from .media import MediaError, probe_video
from .models import RenderAttempt, RenderJob, User, utcnow
from .queue import ACTIVE_STATUSES, admit_job, lock_owner
from .storage import reservation, usage
from .consent import RIGHTS_VERSION, require_rights
from . import object_store
from .schemas import JobResponse, StyleInfo, UserResponse

# Uvicorn access strings contain raw targets/query text; use the content-free
# request event from TraceMiddleware instead. No customer URL reaches access logs.
import logging
logging.getLogger('uvicorn.access').disabled=True
settings = get_settings()
from .catalog import STYLES, STYLE_IDS
from .uploads import router as uploads_router
from .direct_uploads import router as direct_uploads_router
from .account_deletion import router as account_deletion_router
from .project_analysis import router as project_analysis_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    require_current_schema(engine)
    from .restore_journal import configured
    journal=configured()
    from .restore_replay import require_binding
    require_binding(engine,journal)
    if settings.worker_require_sandbox:
        from .worker_limits import require_unprivileged,require_worker_limits
        from .render_sandbox import require_support
        require_unprivileged();require_worker_limits();require_support()
    if settings.media_backend == 's3':
        object_store.check_bucket()
    yield

app = FastAPI(title="NextPhase Shorts API", version="0.1.0", lifespan=lifespan)
from .observability import TraceMiddleware,bind_job
from .ingress import IngressGuard
app.add_middleware(IngressGuard)
app.add_middleware(TraceMiddleware)
from .restore_journal import RestoreGate
app.add_middleware(RestoreGate)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE"],
                   allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Chunk-SHA256"],
                   expose_headers=["Idempotency-Replayed", "Upload-Offset", "X-Chunk-SHA256"])

app.include_router(uploads_router)
app.include_router(direct_uploads_router)
app.include_router(account_deletion_router)
app.include_router(auth_router)
app.include_router(auth_actions_router)
app.include_router(deletion_router)
app.include_router(project_analysis_router)
from .automatic_analysis import router as english_analysis_router
app.include_router(english_analysis_router)

@app.exception_handler(RequestValidationError)
async def safe_auth_validation(request,error):
    if request.url.path.startswith('/api/v1/auth/'):
        return JSONResponse({'detail':'Invalid authentication request'},status_code=422,headers={'Cache-Control':'no-store'})
    if request.url.path.startswith('/api/v1/jobs/') and request.url.path.endswith(('/analysis/review','/analysis/previews')):
        return JSONResponse({'detail':'Invalid review request'},status_code=422,headers={'Cache-Control':'no-store'})
    return await request_validation_exception_handler(request,error)

@app.get("/health")
def health():
    return {"ok": True, "service": "nextphase-shorts", "stage": "baseline-renderer"}

@app.get('/ready')
def ready():
    try:
        require_current_schema(engine)
        from .restore_journal import configured
        journal=configured()
        from .restore_replay import require_binding
        require_binding(engine,journal)
    except (SQLAlchemyError,RuntimeError):
        return JSONResponse({'ok':False,'service':'nextphase-shorts'},status_code=503,
                            headers={'Cache-Control':'no-store'})
    return JSONResponse({'ok':True,'service':'nextphase-shorts'},headers={'Cache-Control':'no-store'})

@app.get("/api/v1/styles", response_model=list[StyleInfo])
def styles():
    # Visual styles are future presets; Stage 1 renderer treats them identically.
    return [StyleInfo(id=k, name=n, description=d, available=False) for k, n, d in STYLES]

@app.get("/api/v1/me", response_model=UserResponse)
def me(user: User = Depends(current_user)):
    return user

@app.get('/api/v1/me/storage')
def storage_usage(user:User=Depends(current_user),db:Session=Depends(session_dep)):
    lock_owner(db,user.id)
    return usage(db,user.id)

@app.get("/api/v1/jobs", response_model=list[JobResponse])
def list_jobs(user: User = Depends(current_user), db: Session = Depends(session_dep)):
    return db.scalars(select(RenderJob).where(RenderJob.user_id == user.id, RenderJob.status != 'deleted', RenderJob.operation != 'analysis')
                      .order_by(RenderJob.created_at.desc()).limit(100)).all()

@app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(session_dep)):
    job = db.scalar(select(RenderJob).where(RenderJob.id == job_id, RenderJob.user_id == user.id, RenderJob.status != 'deleted'))
    if job is None:
        raise HTTPException(404, "Project not found")
    return job

@app.get("/api/v1/jobs/{job_id}/download")
def download(job_id: str, user: User = Depends(current_user), db: Session = Depends(session_dep)):
    job = db.scalar(select(RenderJob).where(RenderJob.id == job_id, RenderJob.user_id == user.id, RenderJob.status != 'deleted'))
    if job is None:
        raise HTTPException(404, "Project not found")
    bind_job(job)
    if job.status != "succeeded" or not job.output_path:
        raise HTTPException(409, "Video is not ready")
    if job.media_backend == 's3':
        key = object_store.output_key(user.id, job.id, job.claim_token)
        try:
            object_store.require_namespace(job.object_store_id)
            remote = object_store.open_object(job.output_path, key, job.max_render_bytes or settings.max_render_bytes)
        except object_store.ObjectStoreError:
            raise HTTPException(503, 'Private video storage is temporarily unavailable')
        def chunks():
            sent = 0
            try:
                for chunk in remote['Body'].iter_chunks(chunk_size=65536):
                    sent += len(chunk)
                    if sent > remote['ContentLength']:
                        raise object_store.ObjectStoreError('Private video length mismatch')
                    yield chunk
            finally:
                remote['Body'].close()
        # Keep bearer credentials on this API origin. No cross-origin redirects.
        return StreamingResponse(chunks(), media_type='video/mp4', background=BackgroundTask(remote['Body'].close), headers={
            'Content-Length': str(remote['ContentLength']), 'Cache-Control': 'private, no-store',
            'Content-Disposition': 'attachment; filename="nextphase-short.mp4"'})
    directory = settings.storage_dir / user.id / job.id
    # Legacy successes keep their original path; new attempts are fenced by token.
    output = directory / job.claim_token / "output.mp4" if job.claim_token else directory / "output.mp4"
    if str(output.resolve()) != str(Path(job.output_path).resolve()) or not output.is_file():
        raise HTTPException(404, "Video file is unavailable")
    return FileResponse(output, media_type="video/mp4", filename="nextphase-short.mp4",
                        headers={"Cache-Control":"private, no-store"})


@app.post('/api/v1/jobs/{job_id}/download-link')
def download_link(job_id: str, response: Response, user: User = Depends(current_user),
                  db: Session = Depends(session_dep)):
    job = db.scalar(select(RenderJob).where(RenderJob.id == job_id, RenderJob.user_id == user.id,
                                           RenderJob.status != 'deleted'))
    if job is None:
        raise HTTPException(404, 'Project not found')
    if job.status != 'succeeded' or not job.output_path:
        raise HTTPException(409, 'Video is not ready')
    if job.media_backend != 's3':
        raise HTTPException(409, 'This development video uses authenticated API download')
    try:
        object_store.require_namespace(job.object_store_id)
        key = object_store.output_key(user.id, job.id, job.claim_token)
        url = object_store.signed_download(job.output_path, key)
    except object_store.ObjectStoreError:
        raise HTTPException(503, 'Private video storage is temporarily unavailable')
    response.headers['Cache-Control'] = 'private, no-store'
    return {'url': url, 'expires_in_seconds': settings.signed_download_seconds}

@app.post("/api/v1/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(session_dep)):
    lock_owner(db, user.id)
    job = db.execute(update(RenderJob).where(
        RenderJob.id == job_id, RenderJob.user_id == user.id,
        RenderJob.status.in_(ACTIVE_STATUSES)).values(
            status='cancelled', finished_at=utcnow(), claim_token=None,
            lease_expires_at=None, error_code=None, output_path=None,
            output_duration_seconds=None).returning(RenderJob)).scalar_one_or_none()
    if job is None:
        job = db.scalar(select(RenderJob).where(RenderJob.id == job_id, RenderJob.user_id == user.id, RenderJob.status != 'deleted'))
        if job is None:
            raise HTTPException(404, 'Project not found')
        if job.status != 'cancelled':
            raise HTTPException(409, 'Only queued or processing jobs can be cancelled')
    db.execute(update(RenderAttempt).where(RenderAttempt.job_id == job_id,
        RenderAttempt.status == 'running').values(status='cancelled',finished_at=utcnow()))
    db.commit()
    return job


@app.post("/api/v1/jobs", response_model=JobResponse, status_code=201)
async def create_job(
    response: Response,
    file: Annotated[UploadFile, File(description="Video file, <=300 MiB")],
    rights_confirmed: Annotated[str, Form()],
    consent_version: Annotated[str, Form()],
    style: Annotated[str, Form()] = "vlog",
    desired_seconds: Annotated[int, Form(ge=5, le=60)] = 30,
    title: Annotated[str, Form(min_length=1, max_length=120)] = "My Short",
    idempotency_key: Annotated[str | None, Header(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")] = None,
    user: User = Depends(upload_user),
    db: Session = Depends(session_dep),
):
    source = directory = None
    committed_new_job = False
    remote_attempt = False
    try:
        require_rights(rights_confirmed == 'true',consent_version)
        acknowledged_at=utcnow()
        if style not in STYLE_IDS:
            raise HTTPException(422, "Unknown editing style")
        ext = Path(file.filename or "").suffix.lower()
        if ext not in {".mp4", ".mov", ".webm", ".m4v"}:
            raise HTTPException(415, "Video must be MP4, MOV, M4V or WebM")
        title = title.strip()
        if not title:
            raise HTTPException(422, "Project title must not be blank")
        job_id = str(uuid.uuid4())
        directory = settings.storage_dir / user.id / job_id
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / ("input" + ext)
        total = 0
        digest = hashlib.sha256()
        with source.open("xb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(413, "File exceeds the 300 MiB MVP upload limit")
                handle.write(chunk)
                digest.update(chunk)
        if total == 0:
            raise HTTPException(422, "Empty video file")
        try:
            info = probe_video(source)
        except MediaError:
            raise HTTPException(422, "File does not contain a supported video")
        if info["duration"] > settings.max_source_seconds:
            raise HTTPException(422, "Source video exceeds 10-minute MVP limit")
        fingerprint = hashlib.sha256(json.dumps({
            'sha256': digest.hexdigest(), 'extension': ext, 'style': style,
            'title': title, 'desired_seconds': desired_seconds}, sort_keys=True).encode()).hexdigest()
        source_reference = str(source.resolve())
        if settings.media_backend == 's3':
            remote_attempt = True
            try:
                source_reference = object_store.put(source, object_store.source_key(user.id, job_id, ext), settings.max_upload_bytes)
            except object_store.ObjectStoreError:
                raise HTTPException(503, 'Private storage is temporarily unavailable; retry this upload')
        candidate = RenderJob(media_backend=settings.media_backend,rights_version=RIGHTS_VERSION,rights_confirmed_at=acknowledged_at,id=job_id, user_id=user.id, title=title, style=style,
                              object_store_id=object_store.namespace_id() if settings.media_backend == 's3' else None,
                              desired_seconds=desired_seconds, source_duration_seconds=info["duration"],
                              source_path=source_reference, status="queued",
                              storage_reserved_bytes=reservation(total,settings.max_render_bytes), max_render_bytes=settings.max_render_bytes,
                              idempotency_key=idempotency_key, request_hash=fingerprint if idempotency_key else None)
        job, replayed = admit_job(db, candidate,source_bytes=total)
        # Retain a new source if COMMIT acknowledgement is lost: DB outcome may
        # be unknown. An orphan is safer than deleting an accepted job's input.
        committed_new_job = not replayed
        db.commit()
        if job.media_backend == 's3':
            source.unlink(missing_ok=True)
        if replayed:
            response.status_code = 200
            response.headers['Idempotency-Replayed'] = 'true'
        return job
    except Exception:
        db.rollback()
        raise
    finally:
        if remote_attempt and not committed_new_job:
            object_store.discard_unaccepted(user.id, job_id)
        # Replays/rejections never leave a second source; an accepted job retains it
        # even if response delivery later fails. No I/O holds the owner-row lock.
        if not committed_new_job and source:
            source.unlink(missing_ok=True)
            try:
                directory.rmdir()
            except OSError:
                pass
        await file.close()
