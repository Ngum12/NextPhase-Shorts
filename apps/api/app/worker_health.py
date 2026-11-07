"""Independent liveness pulses, never a render progress signal or lease renewal."""
from threading import Event,Lock,Thread
import uuid
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from .db import SessionLocal
from .models import WorkerPulse,utcnow
from .worker_events import PHASES,emit


class WorkerHeartbeat:
    def __init__(self,seconds):
        if not 0<seconds<=60:raise ValueError('Heartbeat interval must be positive and <=60 seconds')
        self.seconds=seconds;self.id=str(uuid.uuid4());self._phase='starting'
        self._lock=Lock();self._stop=Event();self._thread=None

    def phase(self,value):
        if value not in PHASES:raise ValueError('Unknown worker phase')
        with self._lock:self._phase=value

    def beat(self):
        with self._lock:phase=self._phase
        try:
            with SessionLocal.begin() as db:
                db.execute(update(WorkerPulse).where(WorkerPulse.id==self.id,WorkerPulse.stopped_at.is_(None))
                    .values(heartbeat_at=utcnow(),phase=phase))
            return True
        except SQLAlchemyError:
            emit('heartbeat_unavailable',worker_id=self.id)
            return False

    def _run(self):
        while not self._stop.wait(self.seconds):self.beat()

    def __enter__(self):
        now=utcnow()
        with SessionLocal.begin() as db:
            db.add(WorkerPulse(id=self.id,started_at=now,heartbeat_at=now,
                phase='starting',heartbeat_seconds=self.seconds))
        self._thread=Thread(target=self._run,name='nextphase-heartbeat',daemon=True)
        self._thread.start()
        emit('worker_started',worker_id=self.id,phase='starting')
        return self

    def __exit__(self,*_):
        self.phase('stopping');self._stop.set()
        self._thread.join(timeout=5)
        try:
            with SessionLocal.begin() as db:
                db.execute(update(WorkerPulse).where(WorkerPulse.id==self.id)
                    .values(heartbeat_at=utcnow(),stopped_at=utcnow(),phase='stopped'))
        except SQLAlchemyError:emit('heartbeat_unavailable',worker_id=self.id)
        emit('worker_stopped',worker_id=self.id,phase='stopped')
