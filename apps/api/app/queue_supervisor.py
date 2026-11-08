"""Bounded durable dispatch reconciliation and expired-lease recovery."""
import argparse
import asyncio
import json
import signal
import time
from sqlalchemy import select,func
from . import broker
from .config import get_settings
from .db import engine,SessionLocal
from .migrate import require_current_schema
from .models import QueueSignal,DeadLetter
from .worker import recover_stale_jobs
from .worker_events import emit


def report():
    with SessionLocal() as db:
        return {'schema_version':1,'backend':get_settings().queue_backend,
            'unpublished':db.scalar(select(func.count()).select_from(QueueSignal).where(
                QueueSignal.published_at.is_(None),QueueSignal.completed_at.is_(None))),
            'unfinished_signals':db.scalar(select(func.count()).select_from(QueueSignal).where(QueueSignal.completed_at.is_(None))),
            'dead_letters':db.scalar(select(func.count()).select_from(DeadLetter)),
            'scope':'private dispatch snapshot; broker acceptance is not render completion'}


async def run(once=False):
    if get_settings().queue_backend!='valkey':raise RuntimeError('Enable the Valkey queue before starting supervisor')
    require_current_schema(engine);stopped=asyncio.Event();redis=None
    for sig in (signal.SIGINT,signal.SIGTERM):
        try:asyncio.get_running_loop().add_signal_handler(sig,stopped.set)
        except NotImplementedError:signal.signal(sig,lambda *_:stopped.set())
    last_maintenance=0
    try:
        while not stopped.is_set():
            try:
                if time.monotonic()-last_maintenance>=60:
                    await asyncio.to_thread(maintenance);last_maintenance=time.monotonic()
                await asyncio.to_thread(recover_stale_jobs)
                await asyncio.to_thread(broker.reconcile)
                if redis is None:redis=await broker.connect()
                await broker.dispatch(redis)
            except Exception:
                emit('queue_unavailable')
                if redis:
                    try:await redis.aclose()
                    except Exception:pass
                    redis=None
                if once:return False
            if once:return True
            try:await asyncio.wait_for(stopped.wait(),timeout=2)
            except asyncio.TimeoutError:pass
    finally:
        if redis:await redis.aclose()
    return True


def maintenance():
    from .upload_cleanup import cleanup_uploads
    from .auth_limits import cleanup_auth
    from .deletion import cleanup_deleted
    from .account_deletion import cleanup_accounts
    cleanup_uploads();cleanup_auth();cleanup_deleted();cleanup_accounts()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');parser.add_argument('--report',action='store_true')
    args=parser.parse_args()
    if args.report:print(json.dumps(report(),indent=2));return
    try:
        if not asyncio.run(run(args.once)):raise SystemExit(1)
    except (KeyboardInterrupt,asyncio.CancelledError):pass


if __name__=='__main__':main()
