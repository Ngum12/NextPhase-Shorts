"""FastAPI starter. Payment access is DISABLED. No AI editing is claimed in Phase 1."""
import hashlib
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .auth import current_user, make_password_hash, make_token, verify_password
from .config import get_settings
from .db import engine, session_dep
from .migrate import require_current_schema
from .media import MediaError, probe_video
from .models import RenderJob, User, utcnow
from .queue import ACTIVE_STATUSES, admit_job, lock_owner
from .schemas import JobResponse, RegisterRequest, StyleInfo, TokenResponse, UserResponse

settings = get_settings()
STYLES = [
    ("documentary", "Cinematic Documentary", "Editorial storytelling, B-roll and evidence"),
    ("vlog", "Professional Vlog", "Clean cuts, tone and pacing"),
    ("reels", "Viral Shorts & Reels", "Dynamic hooks and captions"),
    ("ads", "Product & Business Ads", "Branded promotional short videos"),
    ("education", "Education & Explainers", "Clear concepts and animated diagrams"),
    ("interviews", "Interviews & Podcasts", "Speaker-focused editing and highlights"),
]
STYLE_IDS = {s[0] for s in STYLES}

@asynccontextmanager
async def lifespan(app: FastAPI):
    require_current_schema(engine)
    yield

app = FastAPI(title="NextPhase Shorts API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_credentials=False, allow_methods=["GET", "POST"],
                   allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
                   expose_headers=["Idempotency-Replayed"])

@app.get("/health")
def health():
    return {"ok": True, "service": "nextphase-shorts", "stage": "baseline-renderer"}

@app.get("/api/v1/styles", response_model=list[StyleInfo])
def styles():
    # Visual styles are future presets; Stage 1 renderer treats them identically.
    return [StyleInfo(id=k, name=n, description=d, available=False) for k, n, d in STYLES]

@app.post("/api/v1/auth/register", response_model=TokenResponse, status_code=201)
def register(data: RegisterRequest, db: Session = Depends(session_dep)):
    user = User(email=str(data.email).strip().lower(), password_hash=make_password_hash(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists")
    db.refresh(user)
    return TokenResponse(access_token=make_token(user.id))

class LoginBody(BaseModel):
    email: str
    password: str

@app.post("/api/v1/auth/login", response_model=TokenResponse)
def login(data: LoginBody, db: Session = Depends(session_dep)):
    user = db.scalar(select(User).where(User.email == data.email.strip().lower()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return TokenResponse(access_token=make_token(user.id))

@app.get("/api/v1/me", response_model=UserResponse)
def me(user: User = Depends(current_user)):
    return user

@app.get("/api/v1/jobs", response_model=list[JobResponse])
def list_jobs(user: User = Depends(current_user), db: Session = Depends(session_dep)):
    return db.scalars(select(RenderJob).where(RenderJob.user_id == user.id)
                      .order_by(RenderJob.created_at.desc()).limit(100)).all()

@app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, user: User = Depends(current_user), db: Session = Depends(session_dep)):
    job = db.scalar(select(RenderJob).where(RenderJob.id == job_id, RenderJob.user_id == user.id))
    if job is None:
        raise HTTPException(404, "Project not found")
    return job

@app.get("/api/v1/jobs/{job_id}/download")
def download(job_id: str, user: User = Depends(current_user), db: Session = Depends(session_dep)):
    job = db.scalar(select(RenderJob).where(RenderJob.id == job_id, RenderJob.user_id == user.id))
    if job is None:
        raise HTTPException(404, "Project not found")
    if job.status != "succeeded" or not job.output_path:
        raise HTTPException(409, "Video is not ready")
    directory = settings.storage_dir / user.id / job.id
    # Legacy successes keep their original path; new attempts are fenced by token.
    output = directory / job.claim_token / "output.mp4" if job.claim_token else directory / "output.mp4"
    if str(output.resolve()) != str(Path(job.output_path).resolve()) or not output.is_file():
        raise HTTPException(404, "Video file is unavailable")
    return FileResponse(output, media_type="video/mp4", filename="nextphase-short.mp4")

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
        job = db.scalar(select(RenderJob).where(RenderJob.id == job_id, RenderJob.user_id == user.id))
        if job is None:
            raise HTTPException(404, 'Project not found')
        if job.status != 'cancelled':
            raise HTTPException(409, 'Only queued or processing jobs can be cancelled')
    db.commit()
    return job


@app.post("/api/v1/jobs", response_model=JobResponse, status_code=201)
async def create_job(
    response: Response,
    file: Annotated[UploadFile, File(description="Video file, <=300 MiB")],
    style: Annotated[str, Form()] = "vlog",
    desired_seconds: Annotated[int, Form(ge=5, le=60)] = 30,
    title: Annotated[str, Form(min_length=1, max_length=120)] = "My Short",
    idempotency_key: Annotated[str | None, Header(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")] = None,
    user: User = Depends(current_user),
    db: Session = Depends(session_dep),
):
    source = directory = None
    committed_new_job = False
    try:
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
        candidate = RenderJob(id=job_id, user_id=user.id, title=title, style=style,
                              desired_seconds=desired_seconds, source_duration_seconds=info["duration"],
                              source_path=str(source.resolve()), status="queued",
                              idempotency_key=idempotency_key, request_hash=fingerprint if idempotency_key else None)
        job, replayed = admit_job(db, candidate)
        # Retain a new source if COMMIT acknowledgement is lost: DB outcome may
        # be unknown. An orphan is safer than deleting an accepted job's input.
        committed_new_job = not replayed
        db.commit()
        if replayed:
            response.status_code = 200
            response.headers['Idempotency-Replayed'] = 'true'
        return job
    except Exception:
        db.rollback()
        raise
    finally:
        # Replays/rejections never leave a second source; an accepted job retains it
        # even if response delivery later fails. No I/O holds the owner-row lock.
        if not committed_new_job and source:
            source.unlink(missing_ok=True)
            try:
                directory.rmdir()
            except OSError:
                pass
        await file.close()
