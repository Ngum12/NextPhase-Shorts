"""Conservative admission budgets, not filesystem quotas or subscription credits."""
import argparse
import os
import uuid
from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from .config import get_settings
from .db import SessionLocal, engine
from .models import RenderJob, UploadSession

MAX_RENDER_ATTEMPTS=2


def reservation(source_bytes, render_cap):
    return source_bytes+MAX_RENDER_ATTEMPTS*render_cap


def charged_jobs():
    return or_(RenderJob.status!='deleted',RenderJob.media_deleted_at.is_(None))


def charged_sessions():
    return or_(UploadSession.status=='uploading',and_(UploadSession.status.in_(['expired','aborted']),
        UploadSession.parts_cleaned.is_(False)))


def usage(db,owner_id):
    known=unknown=0
    for model,condition in ((RenderJob,charged_jobs()),(UploadSession,charged_sessions())):
        amount,missing=db.execute(select(func.coalesce(func.sum(model.storage_reserved_bytes),0),
            func.count().filter(or_(model.storage_reserved_bytes.is_(None),model.max_render_bytes.is_(None)))).where(model.user_id==owner_id,condition)).one()
        known+=int(amount);unknown+=missing
    limit=get_settings().account_storage_bytes
    return dict(limit_bytes=limit,known_reserved_bytes=known,uninventoried_count=unknown,
                available_bytes=None if unknown else max(0,limit-known))


def require_capacity(db,owner_id,amount):
    # Caller holds the same owner-row lock used by admission/deletion.
    current=usage(db,owner_id)
    if current['uninventoried_count']:
        raise HTTPException(409,'Storage usage is being verified. New uploads are temporarily unavailable.')
    from .capacity import admit
    admit(db,amount)
    if amount>current['available_bytes']:
        raise HTTPException(409,'Your server storage budget is full. Delete projects or discard pending uploads, then wait for server cleanup.')


def measured_tree(owner_id,job_id):
    if any(str(uuid.UUID(value))!=value for value in (owner_id,job_id)):
        raise ValueError('Noncanonical identity')
    parent=get_settings().storage_dir/owner_id
    root=parent/job_id
    for path in (parent,root):
        if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise ValueError('Unsafe tree')
    if not root.is_dir():raise ValueError('Missing project tree')
    total=source=0
    def scan_failed(error):raise error
    for directory,dirs,files in os.walk(root,followlinks=False,onerror=scan_failed):
        from pathlib import Path
        for name in dirs+files:
            path=Path(directory)/name
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise ValueError('Unsafe tree')
        for name in files:
            path=Path(directory)/name;size=path.stat().st_size;total+=size
            if path.parent==root and name in ('input.mp4','input.mov','input.m4v','input.webm'):source+=size
    return total,source


def reconcile():
    # Offline operator command only: API/workers must be stopped to avoid racing I/O.
    done=missing=0;cap=get_settings().max_render_bytes
    with SessionLocal.begin() as db:
        for row in db.scalars(select(RenderJob).where(or_(RenderJob.storage_reserved_bytes.is_(None),RenderJob.max_render_bytes.is_(None)))):
            if row.status=='deleted' and row.media_deleted_at is not None:
                row.storage_reserved_bytes=0;row.max_render_bytes=cap;done+=1;continue
            if row.media_backend == 's3':
                # Local scratch does not inventory retained remote originals.
                missing+=1;continue
            try:total,source=measured_tree(row.user_id,row.id)
            except (OSError,ValueError):missing+=1;continue
            remaining=max(0,MAX_RENDER_ATTEMPTS-row.attempt_count) if row.status in ('queued','processing') else 0
            row.storage_reserved_bytes=max(total+remaining*cap,reservation(source,cap));row.max_render_bytes=cap;done+=1
        for row in db.scalars(select(UploadSession).where(or_(UploadSession.storage_reserved_bytes.is_(None),UploadSession.max_render_bytes.is_(None)))):
            row.storage_reserved_bytes=reservation(row.total_bytes * (3 if row.transfer_backend == 'direct-s3' else 1),cap);row.max_render_bytes=cap;done+=1
    return done,missing


def main():
    parser=argparse.ArgumentParser(description='Offline storage inventory; stop API and workers first.')
    parser.add_argument('--reconcile',action='store_true',required=True)
    parser.parse_args()
    from .migrate import require_current_schema
    require_current_schema(engine)
    done,missing=reconcile()
    print(f'Inventoried {done} records; {missing} project trees remain unverified. No media deleted.')
    if missing:raise SystemExit(1)


if __name__=='__main__':main()
