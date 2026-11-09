"""Private bounded local OTLP/alert receiver. No public metrics or messages to people.

Not a replacement for a production observability backend/notification service.
"""
from datetime import datetime,timedelta,timezone
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
from fastapi import FastAPI,Request,HTTPException
from .secret_config import read_secret
from .observability import STAGES,FIELDS,validate_fields

logging.getLogger('uvicorn.access').disabled=True
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
ISSUES={'no_fresh_workers','expired_processing_claims','missing_processing_deadlines','worker_clock_skew','worker_inventory_truncated',
    'stale_ingress_reservations','local_disk_low_or_unavailable','global_storage_inventory_unknown','queue_wait_threshold',
    'render_failure_threshold','measurement_inventory_truncated','cost_rates_missing','observed_cost_threshold','cost_coverage_incomplete','provider_budget','budget_input_missing','budget_admission_paused'}


def validate_traces(payload):
    if set(payload)!={'resourceSpans'} or len(payload['resourceSpans'])!=1:raise ValueError()
    resource=payload['resourceSpans'][0]
    if set(resource)!={'resource','scopeSpans'} or resource['resource']!={'attributes':[{'key':'service.name','value':{'stringValue':'nextphase-shorts'}}]} or len(resource['scopeSpans'])!=1:raise ValueError()
    scope=resource['scopeSpans'][0]
    if set(scope)!={'scope','spans'} or scope['scope']!={'name':'nextphase.safe','version':'1'} or len(scope['spans'])>10000:raise ValueError()
    for span in scope['spans']:
        required={'traceId','spanId','name','kind','startTimeUnixNano','endTimeUnixNano','attributes','status'}
        if not required<=set(span) or not set(span)<=required|{'parentSpanId'} or span['name'] not in STAGES or span['kind'] not in (1,2):raise ValueError()
        for name,size in (('traceId',32),('spanId',16),('parentSpanId',16)):
            if name in span and not re.fullmatch('[0-9a-f]{'+str(size)+'}',span[name]):raise ValueError()
        for name in ('startTimeUnixNano','endTimeUnixNano'):
            if not isinstance(span[name],str) or not span[name].isdigit() or len(span[name])>20:raise ValueError()
        if int(span['startTimeUnixNano'])>int(span['endTimeUnixNano']) or span['status'] not in ({'code':1},{'code':2}):raise ValueError()
        fields={}
        for attribute in span['attributes']:
            if set(attribute)!={'key','value'} or not attribute['key'].startswith('nextphase.'):raise ValueError()
            name=attribute['key'][10:]
            if name in fields or name not in FIELDS:raise ValueError()
            value=attribute['value']
            if len(value)!=1:raise ValueError()
            kind,data=next(iter(value.items()))
            if kind=='intValue' and isinstance(data,str) and re.fullmatch('[0-9]{1,19}',data):fields[name]=int(data)
            elif kind=='doubleValue' and type(data) in (int,float):fields[name]=data
            elif kind=='boolValue' and type(data) is bool:fields[name]=data
            else:raise ValueError()
        validate_fields(fields)
    return len(scope['spans'])


def persist(kind,identity,raw,count):
    root=Path(os.environ.get('OPERATOR_SINK_DIR','./.data/operator-sink')).absolute()
    if root.is_symlink() or any(p.is_symlink() for p in root.parents):raise ValueError()
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    if os.name=='posix' and (root.stat().st_uid!=os.geteuid() or root.stat().st_mode&0o077):raise ValueError()
    path=root/'received.sqlite3'
    if path.is_symlink() or (path.exists() and path.stat().st_nlink!=1):raise ValueError()
    if path.exists() and path.stat().st_size>20*1024*1024:raise ValueError()
    with sqlite3.connect(path,timeout=5) as db:
        os.chmod(path,0o600)
        db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY,kind TEXT NOT NULL,digest TEXT NOT NULL,created TEXT NOT NULL,count INTEGER NOT NULL,body BLOB NOT NULL)')
        db.execute('DELETE FROM events WHERE created < ?',((datetime.now(timezone.utc)-timedelta(days=7)).isoformat(),))
        digest=hashlib.sha256(raw).hexdigest();old=db.execute('SELECT digest FROM events WHERE id=?',(identity,)).fetchone()
        if old:
            if old[0]!=digest:raise ValueError()
            return
        if db.execute('SELECT count(*) FROM events').fetchone()[0]>=10000:raise ValueError()
        db.execute('INSERT INTO events VALUES (?,?,?,?,?,?)',(identity,kind,digest,datetime.now(timezone.utc).isoformat(),count,raw))


@app.get('/health')
def health():return {'ok':True,'scope':'private local receiver'}


@app.post('/v1/{kind}')
async def receive(kind:str,request:Request):
    if kind not in ('traces','alerts'):raise HTTPException(404,'Not found')
    try:token=read_secret('OPERATOR_RECEIVER_TOKEN','')
    except RuntimeError:raise HTTPException(503,'Receiver unavailable') from None
    if len(token)<32:raise HTTPException(503,'Receiver unavailable')
    if not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+token):raise HTTPException(401,'Unauthorized')
    identity=request.headers.get('x-nextphase-delivery','')
    if not re.fullmatch('[0-9a-f]{64}',identity):raise HTTPException(400,'Invalid delivery')
    raw=bytearray()
    async for block in request.stream():
        if len(raw)+len(block)>2*1024*1024:raise HTTPException(413,'Delivery too large')
        raw.extend(block)
    try:
        payload=json.loads(raw)
        if kind=='traces':count=validate_traces(payload)
        else:
            if set(payload)!={'version','status','issues'} or payload['version']!=1 or payload['status'] not in ('ok','attention_required') or not isinstance(payload['issues'],list) or not set(payload['issues'])<=ISSUES:raise ValueError()
            count=len(payload['issues'])
        persist(kind,identity,bytes(raw),count)
    except Exception:raise HTTPException(400,'Invalid or unavailable delivery') from None
    return {'accepted':True,'kind':kind}
