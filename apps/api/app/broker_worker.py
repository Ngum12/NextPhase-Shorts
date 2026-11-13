"""Arq consumer of bounded fair-drain requests, with JSON-only serialization."""
import asyncio
import logging
import signal
import uuid
from arq import Retry
from arq.worker import Worker
from sqlalchemy.exc import SQLAlchemyError
from . import broker,worker
from .config import get_settings
from .db import engine
from .migrate import require_current_schema
from .worker_health import WorkerHeartbeat
from .worker_events import emit
from .analysis_limits import BROKER_ANALYSIS_OVERHEAD_SECONDS


def dispatch_timeout(settings):
    return max(settings.render_timeout_seconds+390,
               settings.english_analysis_timeout_seconds+BROKER_ANALYSIS_OVERHEAD_SECONDS)


async def render_next(ctx,generation):
    if ctx['job_id']!='np:'+str(uuid.UUID(generation)):raise ValueError('Invalid dispatch identity')
    claimed=None
    try:
        if worker.stop:raise Retry(defer=3)
        if not await asyncio.to_thread(broker.signal_live,generation):return 'stale_signal'
        claimed=await asyncio.to_thread(worker.claim_job)
        if claimed:
            ctx['pulse'].phase('rendering')
            await asyncio.to_thread(worker.process,claimed)
        if not await asyncio.to_thread(broker.complete_signal,generation,claimed):raise Retry(defer=3)
        return 'durable_outcome'
    except SQLAlchemyError:
        emit('database_unavailable',worker_id=ctx['pulse'].id);raise Retry(defer=3) from None
    finally:ctx['pulse'].phase('idle')


async def startup(ctx):
    ctx['pulse']=await asyncio.to_thread(WorkerHeartbeat(get_settings().worker_heartbeat_seconds).__enter__)


async def shutdown(ctx):
    if 'pulse' in ctx:await asyncio.to_thread(ctx['pulse'].__exit__,None,None,None)


async def run():
    settings=get_settings();require_current_schema(engine)
    if settings.queue_backend!='valkey':raise RuntimeError('Enable Valkey before starting the broker worker')
    if settings.env in ('staging','production') and (not settings.worker_require_limits or not settings.worker_require_sandbox):
        raise RuntimeError('Production broker workers require enforced resource and sandbox guards')
    if settings.worker_require_limits:
        from .worker_limits import require_worker_limits,require_unprivileged
        require_unprivileged();require_worker_limits()
    if settings.worker_require_sandbox:
        from .render_sandbox import require_support
        require_support()
    if settings.media_backend=='s3':await asyncio.to_thread(worker.object_store.check_bucket)
    # Third-party task logs must not emit payload reprs or connection exceptions.
    logger=logging.getLogger('arq');logger.handlers=[logging.NullHandler()];logger.propagate=False
    redis=await broker.connect()
    consumer=Worker([render_next],redis_pool=redis,queue_name=broker.QUEUE,max_jobs=1,max_tries=3,
        job_timeout=dispatch_timeout(settings),job_completion_wait=15,keep_result=0,log_results=False,
        on_startup=startup,on_shutdown=shutdown,job_serializer=broker.dumps,job_deserializer=broker.loads,
        health_check_interval=10,health_check_key='np:worker:'+str(uuid.uuid4()))
    def stop(signum,*_):
        worker.request_stop();consumer.handle_sig_wait_for_completion(signum)
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGINT,signal.SIGTERM):
        try:loop.add_signal_handler(sig,stop,sig)
        except NotImplementedError:signal.signal(sig,stop)
    try:await consumer.async_run()
    finally:await consumer.close()


def main():
    try:asyncio.run(run())
    except (KeyboardInterrupt,asyncio.CancelledError):pass
    except Exception:
        emit('queue_unavailable');raise SystemExit(1) from None


if __name__=='__main__':main()
