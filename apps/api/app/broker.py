"""Secret-free JSON dispatch signals. PostgreSQL owns jobs; Valkey owns delivery."""
from datetime import timedelta,timezone
import json
import logging
import uuid
from arq.connections import RedisSettings,create_pool
from sqlalchemy import select,or_,and_,update
from sqlalchemy.exc import SQLAlchemyError
from .config import get_settings
from .db import SessionLocal
from .models import QueueSignal,RenderJob,User,utcnow
from .queue import lock_owner
from .storage import MAX_RENDER_ATTEMPTS

QUEUE='np:render'


def aware(value):return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def dumps(value):
    # No pickle in broker input or results. Error objects never become payloads.
    data=dict(value)
    if 'r' in data and not isinstance(data['r'],(str,int,float,bool,type(None))):data['r']='request_failed'
    return json.dumps(data,separators=(',',':'),allow_nan=False).encode()


def loads(raw):
    if not isinstance(raw,bytes) or len(raw)>4096:raise ValueError('Invalid queue message')
    data=json.loads(raw)
    if (not isinstance(data,dict) or set(data)!=set(('t','f','a','k','et')) or data['f']!='render_next'
            or not isinstance(data['a'],list) or len(data['a'])!=1 or data['k']!={}
            or (data['t'] is not None and (type(data['t']) is not int or not 1<=data['t']<=10))
            or type(data['et']) is not int or not 0<data['et']<2**63):raise ValueError('Invalid queue message')
    if not isinstance(data['a'][0],str) or str(uuid.UUID(data['a'][0]))!=data['a'][0]:raise ValueError('Invalid queue identity')
    return data


async def connect():
    settings=get_settings()
    if settings.queue_backend!='valkey':raise RuntimeError('Enable Valkey before connecting to the queue')
    logger=logging.getLogger('arq');logger.handlers=[logging.NullHandler()];logger.propagate=False
    redis=await create_pool(RedisSettings(host=settings.queue_host,port=settings.queue_port,password=settings.queue_password,
        ssl=settings.queue_tls,ssl_check_hostname=True,ssl_cert_reqs='required',conn_retries=1,conn_timeout=3,
        max_connections=4),job_serializer=dumps,job_deserializer=loads,default_queue_name=QUEUE)
    try:
        configuration=await redis.config_get('appendonly','appendfsync','maxmemory-policy')
        normalized={k.decode() if isinstance(k,bytes) else k:v.decode() if isinstance(v,bytes) else v for k,v in configuration.items()}
        if normalized!={'appendonly':'yes','appendfsync':'always','maxmemory-policy':'noeviction'}:
            raise RuntimeError('Queue requires AOF always and no eviction')
    except BaseException:
        await redis.aclose();raise
    return redis


def reconcile(limit=100):
    if not 1<=limit<=1000:raise ValueError('Queue reconciliation must be 1–1000')
    now=utcnow()
    with SessionLocal() as db:
        jobs=list(db.execute(select(RenderJob.id,RenderJob.user_id).outerjoin(QueueSignal,QueueSignal.job_id==RenderJob.id).where(RenderJob.status=='queued',
            RenderJob.attempt_count<MAX_RENDER_ATTEMPTS,or_(RenderJob.next_attempt_at.is_(None),RenderJob.next_attempt_at<=now),
            or_(QueueSignal.job_id.is_(None),QueueSignal.completed_at.is_not(None),
                and_(QueueSignal.created_at<=now-timedelta(seconds=60),
                    or_(QueueSignal.lease_until.is_(None),QueueSignal.lease_until<=now))))
            .order_by(RenderJob.created_at,RenderJob.id).limit(limit)))
    for identity,owner in jobs:
        with SessionLocal.begin() as db:
            lock_owner(db,owner,allow_deleted=True)
            job=db.get(RenderJob,identity);user=db.get(User,owner)
            if user.deleted_at or job.status!='queued':continue
            row=db.get(QueueSignal,identity)
            if row is None:
                db.add(QueueSignal(job_id=identity,generation=str(uuid.uuid4()),created_at=now,next_publish_at=now))
            elif row.completed_at is not None or (aware(row.created_at)<=now-timedelta(seconds=60) and
                    (row.lease_until is None or aware(row.lease_until)<=now)):
                row.generation=str(uuid.uuid4());row.created_at=now;row.published_at=None;row.completed_at=None
                row.next_publish_at=now;row.lease_token=None;row.lease_until=None
    # Terminal source jobs no longer need a drain signal. Old broker deliveries are harmless.
    with SessionLocal.begin() as db:
        terminal=select(QueueSignal.job_id).join(RenderJob,RenderJob.id==QueueSignal.job_id).where(
            QueueSignal.completed_at.is_(None),RenderJob.status.in_(('succeeded','failed','cancelled','deleted')))
        identities=list(db.scalars(terminal.order_by(QueueSignal.job_id).limit(limit)))
        db.execute(update(QueueSignal).where(QueueSignal.job_id.in_(identities))
            .values(completed_at=now,lease_token=None,lease_until=None))
    return len(jobs)


def claim_signal():
    now=utcnow()
    eligible=(QueueSignal.completed_at.is_(None),QueueSignal.published_at.is_(None),QueueSignal.next_publish_at<=now,
        or_(QueueSignal.lease_until.is_(None),QueueSignal.lease_until<=now))
    with SessionLocal() as db:
        candidate=db.execute(select(QueueSignal.job_id,RenderJob.user_id).join(RenderJob,RenderJob.id==QueueSignal.job_id)
            .where(*eligible,RenderJob.status=='queued').order_by(QueueSignal.next_publish_at,QueueSignal.job_id).limit(1)).first()
    if candidate is None:return None
    with SessionLocal.begin() as db:
        lock_owner(db,candidate.user_id,allow_deleted=True)
        row=db.scalar(select(QueueSignal).where(QueueSignal.job_id==candidate.job_id,*eligible))
        if row is None or db.get(User,candidate.user_id).deleted_at:return None
        row.lease_token=str(uuid.uuid4());row.lease_until=now+timedelta(seconds=15)
        return {'job':row.job_id,'owner':candidate.user_id,'generation':row.generation,'token':row.lease_token}


def publication(work,success):
    now=utcnow()
    with SessionLocal.begin() as db:
        lock_owner(db,work['owner'],allow_deleted=True)
        values={'lease_token':None,'lease_until':None,'next_publish_at':now+timedelta(seconds=5)}
        if success:values['published_at']=now
        db.execute(update(QueueSignal).where(QueueSignal.job_id==work['job'],QueueSignal.generation==work['generation'],
            QueueSignal.lease_token==work['token'],QueueSignal.lease_until>now).values(**values))


async def dispatch(redis,limit=100):
    import asyncio
    count=0
    for _ in range(limit):
        work=await asyncio.to_thread(claim_signal)
        if work is None:break
        try:
            await redis.enqueue_job('render_next',work['generation'],_job_id='np:'+work['generation'],_queue_name=QUEUE,
                _expires=3600)
            # None means same durable job ID was already accepted (lost-reply retry).
        except Exception:
            await asyncio.to_thread(publication,work,False);raise
        await asyncio.to_thread(publication,work,True);count+=1
    return count


def signal_live(generation):
    with SessionLocal() as db:
        return db.scalar(select(QueueSignal.job_id).where(QueueSignal.generation==generation,QueueSignal.completed_at.is_(None))) is not None


def complete_signal(generation,claimed=None):
    with SessionLocal.begin() as db:
        if claimed:
            job=db.get(RenderJob,claimed['id'])
            if job.status=='processing' and job.claim_token==claimed['claim_token']:return False
        db.execute(update(QueueSignal).where(QueueSignal.generation==generation).values(completed_at=utcnow()))
        return True
