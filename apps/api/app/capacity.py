"""SQL-serialized global budgets. Not a filesystem quota or provider billing cap."""
import argparse
from datetime import timedelta
import json
import logging
import shutil
import uuid
from fastapi import HTTPException
from sqlalchemy import func,select,update,delete,or_
from .config import get_settings
from .db import SessionLocal,engine
from .models import CapacityGate,IngressLease,RenderJob,UploadSession,utcnow

logger=logging.getLogger('nextphase.capacity')


def lock(db):
    if db.execute(update(CapacityGate).where(CapacityGate.id==1).values(id=1)).rowcount!=1:
        raise RuntimeError('Capacity gate is unavailable; run migrations')


def disk_available(amount=0):
    settings=get_settings()
    try:free=shutil.disk_usage(settings.storage_dir).free
    except OSError:raise HTTPException(503,'Server capacity is temporarily unavailable',headers={'Retry-After':'30'}) from None
    if free<settings.min_free_disk_bytes+amount:
        raise HTTPException(503,'Server storage is temporarily full; retry later',headers={'Retry-After':'30'})
    return free


def usage(db):
    from .storage import charged_jobs,charged_sessions
    reserved=unknown=0
    for model,condition in ((RenderJob,charged_jobs()),(UploadSession,charged_sessions())):
        amount,missing=db.execute(select(func.coalesce(func.sum(model.storage_reserved_bytes),0),
            func.count().filter(or_(model.storage_reserved_bytes.is_(None),model.max_render_bytes.is_(None)))).where(condition)).one()
        reserved+=int(amount);unknown+=missing
    incoming,count=db.execute(select(func.coalesce(func.sum(IngressLease.reserved_bytes),0),func.count()).select_from(IngressLease)).one()
    active=db.scalar(select(func.count()).select_from(RenderJob).where(RenderJob.status.in_(('queued','processing'))))
    active+=db.scalar(select(func.count()).select_from(UploadSession).where(UploadSession.status=='uploading',UploadSession.expires_at>utcnow()))
    processing=db.scalar(select(func.count()).select_from(RenderJob).where(RenderJob.status=='processing'))
    stale=db.scalar(select(func.count()).select_from(IngressLease).where(IngressLease.deadline_at<=utcnow()))
    return dict(active=active,processing=processing,reserved_bytes=reserved,inflight_reserved_bytes=int(incoming),
                unknown_records=unknown,inflight_uploads=count,stale_ingress_reservations=stale)


def admit(db,amount):
    # Admission callers hold owner first, then global mutex. Never acquire owner
    # locks while holding this global gate. Reductions/cleanup may proceed freely.
    from .budget_control import require_open
    require_open()
    settings=get_settings();lock(db);current=usage(db)
    if current['unknown_records']:
        raise HTTPException(503,'Server storage inventory must be verified before new uploads',headers={'Retry-After':'30'})
    if current['active']>=settings.global_active_limit:
        raise HTTPException(503,'Server queue is full; retry later',headers={'Retry-After':'30'})
    if current['reserved_bytes']+current['inflight_reserved_bytes']+amount>settings.global_storage_bytes:
        raise HTTPException(503,'Server storage budget is full; retry later',headers={'Retry-After':'30'})
    disk_available()


def worker_available(db):
    from .budget_control import require_open
    try:require_open()
    except HTTPException:return False
    lock(db)
    if db.scalar(select(func.count()).select_from(RenderJob).where(RenderJob.status=='processing'))>=get_settings().global_processing_limit:
        return False
    try:disk_available(get_settings().max_render_bytes)
    except HTTPException:return False
    return True


def acquire_ingress(amount):
    settings=get_settings();identity=str(uuid.uuid4());now=utcnow()
    with SessionLocal.begin() as db:
        lock(db);current=usage(db)
        if current['inflight_uploads']>=settings.ingress_limit or current['inflight_reserved_bytes']+amount>settings.global_ingress_bytes:
            raise HTTPException(503,'Server upload capacity is full; retry later',headers={'Retry-After':'30'})
        disk_available(amount+current['inflight_reserved_bytes'])
        db.add(IngressLease(id=identity,reserved_bytes=amount,created_at=now,
            deadline_at=now+timedelta(seconds=settings.ingress_timeout_seconds+120)))
    return identity


def release_ingress(identity):
    from sqlalchemy.exc import SQLAlchemyError
    try:
        with SessionLocal.begin() as db:db.execute(delete(IngressLease).where(IngressLease.id==identity))
    except SQLAlchemyError:logger.warning('ingress_release_deferred')


def report(db):
    settings=get_settings();current=usage(db)
    try:free=disk_available();disk='ok'
    except HTTPException:free=None;disk='low_or_unavailable'
    return {'schema_version':1,**current,'limits':{'active':settings.global_active_limit,
        'processing':settings.global_processing_limit,'storage_bytes':settings.global_storage_bytes,'ingress':settings.ingress_limit},
        'local_free_bytes':free,'disk':disk,'scope':'logical DB reservations plus local free-space guard; not physical/S3 quotas or complete disk inventory'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-stale',action='store_true')
    parser.add_argument('--writers-stopped',action='store_true')
    args=parser.parse_args()
    from .migrate import require_current_schema
    require_current_schema(engine)
    if args.release_stale:
        if not args.writers_stopped:parser.error('Stop all API writers before explicitly releasing stale intake reservations')
        with SessionLocal.begin() as db:
            lock(db);db.execute(delete(IngressLease).where(IngressLease.deadline_at<=utcnow()))
    with SessionLocal() as db:print(json.dumps(report(db),indent=2))

if __name__=='__main__':main()
