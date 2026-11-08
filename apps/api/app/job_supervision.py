"""Claim renewal is distinct from process liveness and has an absolute deadline."""
from datetime import timedelta
from threading import Event,Thread
from sqlalchemy import update,case
from sqlalchemy.exc import SQLAlchemyError
from .config import get_settings
from .db import SessionLocal
from .models import RenderJob,utcnow
from .worker_events import emit


def renew_claim(job):
    now=utcnow();deadline=now+timedelta(seconds=get_settings().worker_lease_seconds)
    with SessionLocal.begin() as db:
        result=db.execute(update(RenderJob).where(RenderJob.id==job['id'],RenderJob.status=='processing',
            RenderJob.claim_token==job['claim_token'],RenderJob.lease_expires_at>now,
            RenderJob.claim_deadline_at>now).values(lease_expires_at=case(
                (RenderJob.claim_deadline_at<deadline,RenderJob.claim_deadline_at),else_=deadline)))
        return result.rowcount==1


class ClaimSupervisor:
    def __init__(self,job):
        self.job=job;self.lost=Event();self._stop=Event();self.thread=None

    def beat(self):
        try:
            if not renew_claim(self.job):self.lost.set();return False
            return True
        except SQLAlchemyError:
            emit('claim_renewal_unavailable',job_id=self.job['id']);return False

    def run(self):
        while not self._stop.wait(get_settings().worker_renew_seconds):
            self.beat()
            if self.lost.is_set():return

    def __enter__(self):
        self.beat()
        self.thread=Thread(target=self.run,name='nextphase-claim',daemon=True);self.thread.start();return self

    def __exit__(self,*_):
        self._stop.set();self.thread.join(timeout=5)
