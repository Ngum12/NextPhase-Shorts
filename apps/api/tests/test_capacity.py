from datetime import timedelta
import json
from types import SimpleNamespace
import anyio
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.capacity import acquire_ingress,release_ingress,usage,admit
from app.config import get_settings
from app.db import SessionLocal
from app.models import IngressLease,RenderJob,Observation,WorkerPulse,utcnow
from app.ingress import IngressGuard
from app.metadata_cleanup import cleanup
from app.worker import claim_job,mark_done
from test_worker import queued_job
from test_api import new_user
from upload_fixtures import RIGHTS_JSON


def session(client,token,key):
    return client.post('/api/v1/upload-sessions',headers={'Authorization':'Bearer '+token,'Idempotency-Key':key},
        json={**RIGHTS_JSON,'file_name':'sample.mp4','total_bytes':8,'title':'Capacity','style':'vlog','desired_seconds':15})


def test_global_slots_across_owners_preserve_replay_and_admitted_completion(client,monkeypatch):
    a=new_user(client);b=new_user(client);monkeypatch.setattr(get_settings(),'global_active_limit',1)
    first=session(client,a,'capacity-owner-a');assert first.status_code==201
    refused=session(client,b,'capacity-owner-b');assert refused.status_code==503 and refused.headers['retry-after']=='30'
    assert session(client,a,'capacity-owner-a').json()['id']==first.json()['id']
    client.post('/api/v1/upload-sessions/'+first.json()['id']+'/abort',headers={'Authorization':'Bearer '+a})
    from app.upload_cleanup import cleanup_uploads
    cleanup_uploads()
    assert session(client,b,'capacity-owner-b').status_code==201


def test_global_storage_unknown_or_over_budget_refuses_other_owner(client,monkeypatch):
    job_id,token=queued_job(client,monkeypatch)
    other=new_user(client)
    with SessionLocal.begin() as db:db.get(RenderJob,job_id).storage_reserved_bytes=None
    assert session(client,other,'unknown-global-key').status_code==503
    with SessionLocal.begin() as db:db.get(RenderJob,job_id).storage_reserved_bytes=100
    monkeypatch.setattr(get_settings(),'global_storage_bytes',1)
    assert session(client,other,'over-budget-key').status_code==503


def test_processing_limit_is_global_not_per_owner(client,monkeypatch):
    first,_=queued_job(client,monkeypatch);second,_=queued_job(client,monkeypatch)
    monkeypatch.setattr(get_settings(),'global_processing_limit',1)
    claimed=claim_job();assert claimed['id'] in (first,second)
    assert claim_job() is None
    assert mark_done(claimed['id'],claimed['claim_token'],error_code='TEST')
    assert claim_job()['id'] in (first,second)


def test_ingress_crash_reservation_stays_charged_until_explicit_recovery(monkeypatch):
    monkeypatch.setattr(get_settings(),'ingress_limit',1)
    lease=acquire_ingress(1024)
    try:
        with SessionLocal.begin() as db:db.get(IngressLease,lease).deadline_at=utcnow()-timedelta(days=1)
        with pytest.raises(HTTPException) as error:acquire_ingress(1024)
        assert error.value.status_code==503
        with SessionLocal() as db:
            current=usage(db);assert current['inflight_uploads']==1 and current['stale_ingress_reservations']==1
    finally:release_ingress(lease)


def test_low_disk_guard_refuses_admission_without_side_effects(monkeypatch):
    monkeypatch.setattr(get_settings(),'min_free_disk_bytes',1024)
    monkeypatch.setattr('app.capacity.shutil.disk_usage',lambda _:SimpleNamespace(free=1023))
    with pytest.raises(HTTPException) as error:acquire_ingress(1)
    assert error.value.status_code==503
    with SessionLocal() as db:assert db.scalar(select(IngressLease.id)) is None


@pytest.mark.parametrize('headers,body,status',[
    ([],b'x'*65537,413),([(b'content-length',b'1')],b'xx',413),
    ([(b'content-length',b'NaN')],b'',400),
    ([(b'content-length',b'1'),(b'content-length',b'1')],b'x',400)])
def test_body_cap_before_application_parsing_and_no_private_echo(headers,body,status):
    messages=[];reached=[]
    async def app(scope,receive,send):
        await receive();reached.append(True)
        await send({'type':'http.response.start','status':200,'headers':[]})
        await send({'type':'http.response.body','body':b'ok'})
    async def receive():return {'type':'http.request','body':body}
    async def send(message):messages.append(message)
    async def run():await IngressGuard(app)({'type':'http','method':'POST','path':'/api/v1/auth/register','headers':headers},receive,send)
    anyio.run(run)
    assert messages[0]['status']==status and not reached
    assert b'x'*20 not in messages[-1]['body']


def test_metadata_retention_is_bounded_and_preserves_live_workers():
    old=utcnow()-timedelta(days=40)
    with SessionLocal.begin() as db:
        for n in range(3):db.add(Observation(id='oldtrace'+str(n).zfill(8),trace_id='a'*32,stage='encode',started_ns=1,ended_ns=2,outcome='ok',attributes='{}'))
        db.add(WorkerPulse(id='stopped-old',started_at=old,heartbeat_at=old,stopped_at=old,phase='stopped',heartbeat_seconds=10))
        db.add(WorkerPulse(id='live-old',started_at=old,heartbeat_at=old,phase='idle',heartbeat_seconds=10))
    result=cleanup(limit=1);assert result['observations']==1 and result['worker_pulses']==1
    with SessionLocal() as db:
        assert db.get(WorkerPulse,'live-old') is not None
        assert db.get(WorkerPulse,'stopped-old') is None
        assert len(list(db.scalars(select(Observation).where(Observation.started_ns==1))))==2
