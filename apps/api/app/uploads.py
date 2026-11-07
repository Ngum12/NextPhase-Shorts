"""Authenticated sequential uploads on a private shared filesystem.

DB offsets are authoritative; immutable checksum-addressed parts precede DB commits.
"""
import asyncio
import hashlib
import json
import logging
import os
import shutil
import uuid
from datetime import timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, Path as PathParam
from pydantic import BaseModel, Field
from starlette.requests import ClientDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_user
from .catalog import STYLE_IDS
from .config import get_settings
from .db import session_dep
from .media import MediaError, probe_video
from .models import RenderJob, UploadPart, UploadSession, User, utcnow
from .queue import active_count, admit_job, lock_owner, reserved_upload_count
from .storage import reservation, require_capacity
from .schemas import JobResponse
from .consent import RIGHTS_VERSION, RightsAcknowledgement

router = APIRouter(prefix='/api/v1/upload-sessions', tags=['uploads'])
settings = get_settings()
logger = logging.getLogger('nextphase.uploads')
KeyHeader = Annotated[str, Header(min_length=8, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')]


class SessionRequest(RightsAcknowledgement):
    file_name: str = Field(min_length=1, max_length=255)
    total_bytes: int = Field(gt=0, le=314572800, strict=True)
    title: str = Field(default='My Short', min_length=1, max_length=120)
    style: str = 'vlog'
    desired_seconds: int = Field(default=30, ge=5, le=60, strict=True)


def aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def state(row):
    if row.status == 'uploading' and aware(row.expires_at) <= utcnow():
        return 'expired'
    return row.status


def view(row):
    return dict(id=row.id, status=state(row), file_name=row.file_name,
                total_bytes=row.total_bytes, received_bytes=row.received_bytes,
                chunk_bytes=row.chunk_bytes, expires_at=aware(row.expires_at),
                title=row.title, style=row.style, desired_seconds=row.desired_seconds,
                job_id=row.job_id, source_sha256=row.source_sha256,
                rights_version=row.rights_version,rights_confirmed_at=aware(row.rights_confirmed_at) if row.rights_confirmed_at else None)


def owned(db, session_id, user_id):
    row = db.scalar(select(UploadSession).where(UploadSession.id == session_id,
                    UploadSession.user_id == user_id).execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, 'Upload session not found')
    if row.status == 'deleted':
        raise HTTPException(410, 'This upload belongs to a deleted project.')
    return row


def require_uploading(row):
    status = state(row)
    if status == 'expired':
        raise HTTPException(410, 'Upload session expired. Start a new upload.')
    if status != 'uploading':
        raise HTTPException(409, 'Upload session is no longer accepting data')
    if row.rights_version!=RIGHTS_VERSION or row.rights_confirmed_at is None:
        raise HTTPException(409,'Confirm upload rights before resuming this upload.')


def part_directory(user_id, session_id):
    return settings.storage_dir / user_id / '.uploads' / session_id


def part_path(user_id, session_id, offset, digest):
    return part_directory(user_id, session_id) / f'{offset}-{digest}.part'


def sync_directory(path):
    if os.name == 'posix':
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def cleanup_parts(user_id, session_id):
    try:
        shutil.rmtree(part_directory(user_id, session_id))
        return True
    except FileNotFoundError:
        return True
    except OSError:
        # A concurrent request may still have an open staging file on Windows.
        logger.warning('upload cleanup deferred session_id=%s', session_id)
        return False


@router.post('', status_code=201)
def create_session(payload: SessionRequest, response: Response, idempotency_key: KeyHeader,
                   user: User = Depends(current_user), db: Session = Depends(session_dep)):
    title = payload.title.strip()
    extension = Path(payload.file_name).suffix.lower()
    if not title or payload.style not in STYLE_IDS:
        raise HTTPException(422, 'Provide a title and a supported style')
    if extension not in {'.mp4', '.mov', '.webm', '.m4v'}:
        raise HTTPException(415, 'Video must be MP4, MOV, M4V or WebM')
    if payload.total_bytes > settings.max_upload_bytes:
        raise HTTPException(413, 'File exceeds the configured upload limit')
    descriptor = payload.model_dump(exclude={'rights_confirmed','consent_version'})
    descriptor['title'] = title
    digest = hashlib.sha256(json.dumps(descriptor, sort_keys=True).encode()).hexdigest()
    lock_owner(db, user.id)
    previous = db.scalar(select(UploadSession).where(UploadSession.user_id == user.id,
                         UploadSession.client_key == idempotency_key))
    if previous:
        if previous.status == 'deleted':
            raise HTTPException(410, 'This upload belongs to a deleted project. Start a new upload.')
        if previous.status=='aborted' and previous.total_bytes==0:
            raise HTTPException(410,'This upload intent was discarded. Start a new upload.')
        if previous.descriptor_hash != digest:
            raise HTTPException(409, 'This upload key was already used with different file details or settings')
        if state(previous)=='uploading' and (previous.rights_version!=RIGHTS_VERSION or previous.rights_confirmed_at is None):
            previous.rights_version=RIGHTS_VERSION;previous.rights_confirmed_at=utcnow()
            db.commit()
        response.status_code = 200
        response.headers['Idempotency-Replayed'] = 'true'
        return view(previous)
    if active_count(db, user.id) + reserved_upload_count(db, user.id) >= settings.max_active_jobs_per_user:
        raise HTTPException(429, 'Your queue is full. Finish or discard a pending upload, or cancel a queued job.',
                            headers={'Retry-After': '5'})
    budget=reservation(payload.total_bytes,settings.max_render_bytes)
    require_capacity(db,user.id,budget)
    row = UploadSession(rights_version=RIGHTS_VERSION,rights_confirmed_at=utcnow(),storage_reserved_bytes=budget,max_render_bytes=settings.max_render_bytes,id=str(uuid.uuid4()), user_id=user.id, client_key=idempotency_key,
                        descriptor_hash=digest, file_name=payload.file_name, extension=extension,
                        title=title, style=payload.style, desired_seconds=payload.desired_seconds,
                        total_bytes=payload.total_bytes, chunk_bytes=settings.upload_chunk_bytes,
                        expires_at=utcnow() + timedelta(hours=settings.upload_session_hours))
    db.add(row)
    db.commit()
    return view(row)


@router.post('/discard-by-key')
def discard_by_key(idempotency_key:KeyHeader,user:User=Depends(current_user),db:Session=Depends(session_dep)):
    # No rights assertion or file details are required merely to discard. A zero-
    # byte aborted tombstone fences an in-flight create whose response was lost.
    lock_owner(db,user.id)
    row=db.scalar(select(UploadSession).where(UploadSession.user_id==user.id,
        UploadSession.client_key==idempotency_key))
    if row is None:
        row=UploadSession(id=str(uuid.uuid4()),user_id=user.id,client_key=idempotency_key,
            descriptor_hash='0'*64,file_name='discarded.mp4',extension='.mp4',title='Discarded upload',
            style='vlog',desired_seconds=30,total_bytes=0,received_bytes=0,
            chunk_bytes=settings.upload_chunk_bytes,status='aborted',parts_cleaned=True,
            storage_reserved_bytes=0,max_render_bytes=settings.max_render_bytes,
            expires_at=utcnow()+timedelta(hours=settings.upload_session_hours))
        db.add(row)
    elif row.status=='deleted':raise HTTPException(410,'This upload belongs to a deleted project.')
    elif row.status!='completed':row.status='expired' if state(row)=='expired' else 'aborted'
    db.commit()
    result=view(row)
    cleanup_parts(user.id,row.id)
    return result


@router.get('/by-key/{client_key}')
def session_by_key(client_key:Annotated[str,PathParam(min_length=8,max_length=128,pattern=r'^[A-Za-z0-9_-]+$')],user:User=Depends(current_user),db:Session=Depends(session_dep)):
    row=db.scalar(select(UploadSession).where(UploadSession.client_key==client_key,UploadSession.user_id==user.id))
    if row is None:raise HTTPException(404,'Upload session not found')
    return view(owned(db,row.id,user.id))


@router.get('/{session_id}')
def get_session(session_id: str, user: User = Depends(current_user), db: Session = Depends(session_dep)):
    return view(owned(db, session_id, user.id))


@router.put('/{session_id}/parts')
async def upload_part(session_id: str, request: Request, response: Response,
                      offset: Annotated[int, Query(ge=0)],
                      checksum: Annotated[str, Header(alias='X-Chunk-SHA256', pattern=r'^[a-fA-F0-9]{64}$')],
                      user: User = Depends(current_user), db: Session = Depends(session_dep)):
    user_id = user.id
    row = owned(db, session_id, user_id)
    require_uploading(row)
    if offset >= row.total_bytes or offset % row.chunk_bytes:
        raise HTTPException(409, 'Chunk offset is not a valid part boundary')
    expected = min(row.chunk_bytes, row.total_bytes - offset)
    db.rollback()  # No transaction/owner lock is held while receiving the network body.
    directory = part_directory(user_id, session_id)
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / (str(uuid.uuid4()) + '.staging')
    digest = hashlib.sha256()
    total = 0
    try:
        with temporary.open('xb') as handle:
            async with asyncio.timeout(settings.upload_part_timeout_seconds):
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > expected:
                        raise HTTPException(413, 'Chunk exceeds the negotiated part size')
                    digest.update(chunk)
                    handle.write(chunk)
            if total != expected:
                raise HTTPException(422, 'Chunk length does not match the negotiated part size')
            if digest.hexdigest() != checksum.lower():
                raise HTTPException(422, 'Chunk checksum does not match')
            handle.flush()
            os.fsync(handle.fileno())
        lock_owner(db, user_id)
        row = owned(db, session_id, user_id)
        require_uploading(row)
        previous = db.get(UploadPart, (session_id, offset))
        if previous:
            if previous.sha256 != digest.hexdigest() or previous.size != total:
                raise HTTPException(409, 'A different chunk is already committed at this offset')
        elif offset != row.received_bytes:
            raise HTTPException(409, 'Query upload progress and resume at the committed offset',
                                headers={'Upload-Offset': str(row.received_bytes)})
        destination = part_path(user_id, session_id, offset, digest.hexdigest())
        os.replace(temporary, destination)
        sync_directory(directory)
        if previous is None:
            db.add(UploadPart(session_id=session_id, offset=offset, size=total, sha256=digest.hexdigest()))
            row.received_bytes += total
        db.commit()
        response.headers['Upload-Offset'] = str(row.received_bytes)
        response.headers['X-Chunk-SHA256'] = digest.hexdigest()
        return view(row)
    except TimeoutError:
        db.rollback()
        raise HTTPException(408, 'Chunk transfer timed out; query progress and retry')
    except ClientDisconnect:
        db.rollback()
        raise HTTPException(400, 'Chunk interrupted; query progress before retrying')
    except Exception:
        db.rollback()
        raise
    finally:
        temporary.unlink(missing_ok=True)


@router.post('/{session_id}/abort')
def abort_session(session_id: str, user: User = Depends(current_user), db: Session = Depends(session_dep)):
    user_id = user.id
    lock_owner(db, user_id)
    row = owned(db, session_id, user_id)
    if row.status == 'completed':
        raise HTTPException(409, 'Upload is complete; cancel the render from the project instead')
    row.status = 'expired' if state(row) == 'expired' else 'aborted'
    db.commit()
    result = view(row)
    cleanup_parts(user_id, session_id)
    return result


@router.post('/{session_id}/complete', response_model=JobResponse)
def complete_session(session_id: str, user: User = Depends(current_user), db: Session = Depends(session_dep)):
    user_id = user.id
    row = owned(db, session_id, user_id)
    if row.status == 'completed':
        cleanup_parts(user_id, session_id)
        return db.get(RenderJob, row.job_id)
    require_uploading(row)
    if row.received_bytes != row.total_bytes:
        raise HTTPException(409, 'Upload is incomplete; query progress and resume')
    snapshot = {key: getattr(row, key) for key in ('total_bytes', 'extension', 'title', 'style', 'desired_seconds')}
    parts = [(part.offset, part.size, part.sha256) for part in db.scalars(
        select(UploadPart).where(UploadPart.session_id == session_id).order_by(UploadPart.offset))]
    db.rollback()
    job_id = str(uuid.uuid4())
    directory = settings.storage_dir / user_id / job_id
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / ('input' + snapshot['extension'])
    retain_source = False
    remote_attempt = False
    try:
        full_hash = hashlib.sha256()
        position = 0
        with source.open('xb') as output:
            for offset, size, checksum in parts:
                if offset != position:
                    raise HTTPException(409, 'Upload parts are not contiguous')
                part_hash = hashlib.sha256()
                copied = 0
                try:
                    with part_path(user_id, session_id, offset, checksum).open('rb') as part:
                        while chunk := part.read(65536):
                            copied += len(chunk)
                            if copied > size:
                                raise HTTPException(409, 'Stored upload part has changed')
                            part_hash.update(chunk)
                            full_hash.update(chunk)
                            output.write(chunk)
                except FileNotFoundError:
                    db.rollback()
                    current = owned(db, session_id, user_id)
                    if current.status == 'completed':
                        return db.get(RenderJob, current.job_id)
                    raise HTTPException(409, 'An upload part is missing; retry its original chunk or discard the upload')
                if copied != size or part_hash.hexdigest() != checksum:
                    raise HTTPException(409, 'Stored upload part failed integrity verification')
                position += copied
            if position != snapshot['total_bytes']:
                raise HTTPException(409, 'Upload byte count does not match')
            output.flush()
            os.fsync(output.fileno())
        sync_directory(directory)
        try:
            media = probe_video(source)
        except MediaError:
            raise HTTPException(422, 'File does not contain a supported video')
        if media['duration'] > settings.max_source_seconds:
            raise HTTPException(422, 'Source video exceeds 10-minute MVP limit')
        from . import object_store
        source_reference = str(source.resolve())
        if settings.media_backend == 's3':
            remote_attempt = True
            try:
                source_reference = object_store.put(source, object_store.source_key(user_id, job_id, snapshot['extension']), settings.max_upload_bytes)
            except object_store.ObjectStoreError:
                raise HTTPException(503, 'Private storage is temporarily unavailable; retry completion')
        lock_owner(db, user_id)
        row = owned(db, session_id, user_id)
        if row.status == 'completed':
            return db.get(RenderJob, row.job_id)
        require_uploading(row)
        candidate = RenderJob(media_backend=settings.media_backend,rights_version=row.rights_version,rights_confirmed_at=row.rights_confirmed_at,id=job_id, user_id=user_id, title=row.title, style=row.style,
                              object_store_id=object_store.namespace_id() if settings.media_backend == 's3' else None,
                              desired_seconds=row.desired_seconds, source_duration_seconds=media['duration'],
                              source_path=source_reference, status='queued',
                              storage_reserved_bytes=row.storage_reserved_bytes or reservation(row.total_bytes,settings.max_render_bytes),
                              max_render_bytes=row.max_render_bytes or settings.max_render_bytes)
        job, _ = admit_job(db, candidate, upload_session_id=session_id)
        row.status, row.job_id, row.source_sha256 = 'completed', job.id, full_hash.hexdigest()
        retain_source = True  # Preserve accepted input even if COMMIT acknowledgement is lost.
        db.commit()
        if job.media_backend == 's3':
            source.unlink(missing_ok=True)
        cleanup_parts(user_id, session_id)
        return job
    except Exception:
        db.rollback()
        raise
    finally:
        if remote_attempt and not retain_source:
            object_store.discard_unaccepted(user_id, job_id)
        if not retain_source:
            source.unlink(missing_ok=True)
            try:
                directory.rmdir()
            except OSError:
                pass
