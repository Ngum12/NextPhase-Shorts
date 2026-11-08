"""Content-free trace recording and OTLP/HTTP JSON export, without a paid service."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass,field
import json
import logging
import math
import secrets
import time
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

STAGES={'http_upload','http_download','http_control','attempt','source_fetch','source_probe','encode','output_probe','output_publish'}
FIELDS={'wall_seconds','cpu_seconds_lower_bound','rss_bytes_sampled_max','frames','frames_per_second',
        'received_bytes','sent_bytes','storage_read_bytes','storage_write_bytes','http_status','io_complete'}
current=ContextVar('nextphase_trace',default=None)
active_attributes=ContextVar('nextphase_stage_attributes',default=None)
logger=logging.getLogger('nextphase.observability')


@dataclass
class Recorder:
    trace_id:str=field(default_factory=lambda:secrets.token_hex(16))
    parent_id:str | None=None
    job_id:str | None=None
    attempt_id:str | None=None
    rows:list=field(default_factory=list)


def validate_fields(attributes):
    if not set(attributes)<=FIELDS:raise ValueError('Unknown observation field')
    for name,value in attributes.items():
        if name=='io_complete':
            if type(value) is not bool:raise ValueError('Invalid completion flag')
        elif isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1e18:
            raise ValueError('Invalid observation measurement')


@contextmanager
def stage(name,**attributes):
    if name not in STAGES:raise ValueError('Unknown observation stage')
    validate_fields(attributes)
    recorder=current.get()
    if recorder is None:
        yield attributes;return
    identity=secrets.token_hex(8);parent=recorder.parent_id
    start=time.time_ns();began=time.monotonic();outcome='ok'
    recorder.parent_id=identity
    attributes_token=active_attributes.set(attributes)
    try:
        yield attributes
    except BaseException:
        outcome='error';raise
    finally:
        recorder.parent_id=parent
        active_attributes.reset(attributes_token)
        attributes['wall_seconds']=max(0,time.monotonic()-began)
        validate_fields(attributes)
        if len(recorder.rows)<32:
            recorder.rows.append(dict(id=identity,trace_id=recorder.trace_id,parent_id=parent,
                job_id=recorder.job_id,attempt_id=recorder.attempt_id,stage=name,started_ns=start,
                ended_ns=max(start,time.time_ns()),outcome=outcome,attributes=json.dumps(attributes,allow_nan=False)))


def bind_job(job):
    recorder=current.get()
    if recorder:
        recorder.job_id=job.id
        if job.trace_id:
            # Existing project requests are linked by trace ID, not bearer/header text.
            recorder.trace_id=job.trace_id
        else:
            job.trace_id=recorder.trace_id;job.parent_span_id=recorder.parent_id


def save(recorder):
    from .models import Observation
    if not recorder.rows:return True
    from .db import SessionLocal
    try:
        with SessionLocal.begin() as db:db.add_all([Observation(**row) for row in recorder.rows])
        return True
    except (SQLAlchemyError,ValueError):
        logger.warning('observation_write_unavailable')
        return False


class TraceMiddleware:
    """Count ASGI bytes actually handed to the server; no bodies/headers/URLs stored."""
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        recorder=Recorder();token=current.set(recorder);received=sent=0;status=500;complete=False
        start=time.time_ns();began=time.monotonic();span_id=secrets.token_hex(8);recorder.parent_id=span_id
        response_started=False;internal_error=False
        async def measured_receive():
            nonlocal received
            message=await receive()
            if message['type']=='http.request':received+=len(message.get('body',b''))
            return message
        async def measured_send(message):
            nonlocal sent,status,complete,response_started
            if message['type']=='http.response.start':
                status=message['status'];response_started=True;message=dict(message)
                message['headers']=[*message.get('headers',[]),(b'x-trace-id',recorder.trace_id.encode())]
            await send(message)
            if message['type']=='http.response.body':
                sent+=len(message.get('body',b''));complete=not message.get('more_body',False)
        try:
            await self.app(scope,measured_receive,measured_send)
        except Exception:
            # Never log exception repr/traceback, request body, headers or raw target.
            internal_error=True
            logger.error('request_internal_error')
            if not response_started:
                await measured_send({'type':'http.response.start','status':500,'headers':[(b'content-type',b'application/json')]})
                await measured_send({'type':'http.response.body','body':b'{"detail":"Request temporarily unavailable"}'})
            elif not complete:
                # Existing Content-Length lets clients detect incomplete streams.
                # A disconnected client may reject even this close; do not expose exception text.
                try:await send({'type':'http.response.body','body':b'','more_body':False})
                except Exception:pass
        finally:
            # Only fixed resource route templates. Never copy raw URL/query/header or exception.
            route=getattr(scope.get('route'),'path','')
            media_route=route.startswith('/api/v1/upload-sessions') or route.startswith('/api/v1/jobs')
            if media_route and (recorder.job_id or 200<=status<300):
                name='http_download' if route.endswith('/download') else 'http_upload' if received else 'http_control'
                recorder.rows.append(dict(id=span_id,trace_id=recorder.trace_id,parent_id=None,job_id=recorder.job_id,
                    attempt_id=None,stage=name,started_ns=start,ended_ns=max(start,time.time_ns()),
                    outcome='ok' if status<400 and complete else 'error',attributes=json.dumps({
                        'wall_seconds':max(0,time.monotonic()-began),'received_bytes':received,
                        'sent_bytes':sent,'http_status':status,'io_complete':complete})))
                # Avoid blocking the event loop on a separate telemetry transaction.
                import anyio
                await anyio.to_thread.run_sync(save,recorder)
            logger.info(json.dumps({'schema_version':1,'component':'api','event':'request_completed',
                'trace_id':recorder.trace_id,'span_id':span_id,'http_status':status,
                'outcome':'error' if internal_error or status>=500 else 'ok',
                'wall_seconds':max(0,time.monotonic()-began)},separators=(',',':')))
            current.reset(token)


def otlp(rows):
    """OTLP JSON mapping: protobuf 64-bit integers encoded as decimal strings."""
    spans=[]
    for row in rows:
        import re
        if not re.fullmatch('[0-9a-f]{32}',row.trace_id) or not re.fullmatch('[0-9a-f]{16}',row.id) or (row.parent_id and not re.fullmatch('[0-9a-f]{16}',row.parent_id)):
            raise ValueError('Invalid stored correlation identity')
        attributes=json.loads(row.attributes);validate_fields(attributes)
        if row.stage not in STAGES:raise ValueError('Unknown stored observation stage')
        def value(v):
            return {'boolValue':v} if type(v) is bool else {'intValue':str(v)} if type(v) is int else {'doubleValue':v}
        span={'traceId':row.trace_id,'spanId':row.id,'name':row.stage,'kind':2 if row.stage.startswith('http_') else 1,
              'startTimeUnixNano':str(row.started_ns),'endTimeUnixNano':str(row.ended_ns),
              'attributes':[{'key':'nextphase.'+k,'value':value(v)} for k,v in sorted(attributes.items())],
              'status':{'code':1 if row.outcome=='ok' else 2}}
        if row.parent_id:span['parentSpanId']=row.parent_id
        spans.append(span)
    return {'resourceSpans':[{'resource':{'attributes':[{'key':'service.name','value':{'stringValue':'nextphase-shorts'}}]},
        'scopeSpans':[{'scope':{'name':'nextphase.safe','version':'1'},'spans':spans}]}]}


def export(db,limit=1000,since_ns=0):
    from .models import Observation
    if not 1<=limit<=10000 or since_ns<0:raise ValueError('Invalid export bound')
    rows=list(db.scalars(select(Observation).where(Observation.started_ns>=since_ns)
        .order_by(Observation.started_ns,Observation.id).limit(limit+1)))
    # Refuse silent truncation. Use explicit time windows or a larger bounded batch.
    if len(rows)>limit:raise ValueError('Trace export truncated; narrow the time window')
    return otlp(rows)
