"""Signed temporary PUTs are never authoritative parts: verify then seal privately."""
from datetime import timedelta
from pathlib import Path
import tempfile
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import object_store as store
from .auth import current_user
from .config import get_settings
from .db import session_dep
from .models import DirectUploadGrant, UploadPart, User, utcnow
from .queue import lock_owner
from .uploads import aware, owned, require_uploading, view

router = APIRouter(prefix='/api/v1/upload-sessions', tags=['direct uploads'])


class PartIntent(BaseModel):
    offset: int = Field(ge=0, strict=True)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


def require_direct(row):
    require_uploading(row)
    if row.transfer_backend != 'direct-s3':
        raise HTTPException(409, 'This session uses API chunk upload')
    try:
        store.require_namespace(row.object_store_id)
    except store.ObjectStoreError:
        raise HTTPException(503, 'Upload storage configuration is unavailable')


@router.post('/{session_id}/part-url')
def part_url(session_id: str, payload: PartIntent, response: Response,
             user: User = Depends(current_user), db: Session = Depends(session_dep)):
    lock_owner(db, user.id)
    row = owned(db, session_id, user.id)
    require_direct(row)
    previous = db.get(UploadPart, (session_id, payload.offset))
    if previous:
        if previous.sha256 != payload.sha256:
            raise HTTPException(409, 'Committed chunk differs from this file')
        response.headers['Cache-Control'] = 'private, no-store'
        return {'committed': True, 'session': view(row)}
    if payload.offset != row.received_bytes or payload.offset >= row.total_bytes:
        raise HTTPException(409, 'Resume at the server acknowledged offset')
    seconds = min(get_settings().signed_upload_seconds, int((aware(row.expires_at)-utcnow()).total_seconds()))
    if seconds < 1:
        raise HTTPException(410, 'Upload session expired')
    grant = db.scalar(select(DirectUploadGrant).where(DirectUploadGrant.session_id == row.id,
                                                    DirectUploadGrant.offset == payload.offset))
    if grant is None:
        grant = DirectUploadGrant(session_id=row.id, offset=payload.offset,
            size=min(row.chunk_bytes, row.total_bytes-payload.offset), sha256=payload.sha256,
            expires_at=utcnow()+timedelta(seconds=seconds))
        db.add(grant); db.flush()
    elif grant.sha256 != payload.sha256:
        raise HTTPException(409, 'This chunk intent already identifies different bytes')
    grant.expires_at = utcnow()+timedelta(seconds=seconds)
    try:
        result = store.signed_part(user.id, row.id, grant.id, grant.size, grant.sha256, seconds)
    except store.ObjectStoreError:
        raise HTTPException(503, 'Signed upload storage is unavailable')
    # Record a conservative deadline after signing, including cold SDK startup.
    grant.expires_at = utcnow()+timedelta(seconds=seconds)
    db.commit()
    response.headers['Cache-Control'] = 'private, no-store'
    return {**result, 'grant_id': grant.id, 'committed': False}


@router.post('/{session_id}/part-commit/{grant_id}')
def commit_part(session_id: str, grant_id: str, user: User = Depends(current_user),
                db: Session = Depends(session_dep)):
    lock_owner(db, user.id)
    row = owned(db, session_id, user.id)
    require_direct(row)
    grant = db.scalar(select(DirectUploadGrant).where(DirectUploadGrant.id == grant_id,
                                                    DirectUploadGrant.session_id == row.id))
    if grant is None:
        raise HTTPException(404, 'Chunk intent not found')
    previous = db.get(UploadPart, (session_id, grant.offset))
    if previous:
        return view(row)
    if grant.offset != row.received_bytes:
        raise HTTPException(409, 'Resume at the server acknowledged offset')
    offset, size, checksum, user_id = grant.offset, grant.size, grant.sha256, user.id
    db.rollback()  # Never hold the owner lock across object I/O.
    try:
        # fetch checks both bounded length and full SHA. Clients can only replace
        # incoming/{grant}, never sealed/{grant}; no mutable key becomes a part.
        with tempfile.TemporaryDirectory(prefix='nextphase-seal-') as directory:
            path = Path(directory)/'part'
            incoming = store.upload_key(user_id, session_id, grant_id)
            store.fetch(store.reference(incoming, checksum), incoming, path, size)
            if path.stat().st_size != size:
                raise store.ObjectStoreError('Chunk length mismatch')
            sealed = store.put(path, store.upload_key(user_id, session_id, grant_id, sealed=True), size)
    except store.ObjectStoreError:
        raise HTTPException(409, 'Chunk is unavailable or failed verification; re-upload it before resuming')
    lock_owner(db, user_id)
    row = owned(db, session_id, user_id)
    require_direct(row)
    previous = db.get(UploadPart, (session_id, offset))
    if previous is None:
        if row.received_bytes != offset:
            raise HTTPException(409, 'Resume at the server acknowledged offset')
        db.add(UploadPart(session_id=session_id, offset=offset, size=size, sha256=checksum,
                          object_reference=sealed, direct_grant_id=grant_id))
        row.received_bytes += size
    db.commit()
    return view(row)
