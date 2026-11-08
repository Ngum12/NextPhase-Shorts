"""Bounded operational-observation retention; never purge media/rights/tombstones."""
from datetime import timedelta
from sqlalchemy import delete,select
from .config import get_settings
from .db import SessionLocal
from .models import Observation,WorkerPulse,utcnow


def cleanup(limit=1000):
    if not 1<=limit<=1000:raise ValueError('Cleanup limit must be 1–1000')
    cutoff=utcnow()-timedelta(days=get_settings().observation_retention_days);removed={}
    with SessionLocal.begin() as db:
        for model,condition in ((Observation,Observation.ended_ns<int(cutoff.timestamp()*1e9)),
                (WorkerPulse,(WorkerPulse.stopped_at.is_not(None)) & (WorkerPulse.heartbeat_at<cutoff))):
            ids=list(db.scalars(select(model.id).where(condition).order_by(model.id).limit(limit)))
            removed[model.__tablename__]=db.execute(delete(model).where(model.id.in_(ids))).rowcount if ids else 0
    return removed
