import asyncio
import json
import pickle
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from arq import Retry
from sqlalchemy import update,select
from app import broker,broker_worker,worker
from app.config import get_settings,Settings
from app.db import SessionLocal
from app.models import RenderJob,RenderAttempt,QueueSignal,DeadLetter,utcnow
from app.job_supervision import renew_claim,ClaimSupervisor
from test_worker import queued_job


@pytest.fixture
def queued(client,monkeypatch):
    # Isolate scheduling fixtures, including uncompleted synthetic prior claims.
    with SessionLocal.begin() as db:
        db.execute(update(RenderJob).where(RenderJob.status.in_(('queued','processing')))
            .values(status='cancelled',claim_token=None,lease_expires_at=None,claim_deadline_at=None))
    monkeypatch.setattr(get_settings(),'queue_backend','valkey')
    identity,_=queued_job(client,monkeypatch)
    return identity


def signal(identity):
    with SessionLocal() as db:return db.get(QueueSignal,identity)


class FakeRedis:
    def __init__(self):self.messages={};self.fail=False;self.lost=False
    async def enqueue_job(self,name,generation,**kwargs):
        if self.fail:raise ConnectionError('synthetic-private-connection-data')
        assert name=='render_next'
        key=kwargs['_job_id'];old=self.messages.get(key);self.messages[key]=generation
        if self.lost:self.lost=False;raise ConnectionError('lost reply')
        return None if old else key


def test_admission_signal_is_durable_and_contains_only_identifiers(queued):
    row=signal(queued);assert row and row.job_id==queued and not row.published_at
    assert str(uuid.UUID(row.generation))==row.generation
    fake=FakeRedis();assert asyncio.run(broker.dispatch(fake))==1
    assert signal(queued).published_at is not None
    assert list(fake.messages)==['np:'+row.generation]


def test_broker_outage_and_lost_publish_reply_do_not_consume_render_attempts(queued):
    fake=FakeRedis();fake.fail=True
    with pytest.raises(ConnectionError):asyncio.run(broker.dispatch(fake))
    with SessionLocal.begin() as db:
        row=db.get(QueueSignal,queued);assert row.published_at is None and row.lease_token is None
        assert db.get(RenderJob,queued).attempt_count==0
        row.next_publish_at=utcnow()-timedelta(seconds=1)
    fake.fail=False;fake.lost=True
    with pytest.raises(ConnectionError):asyncio.run(broker.dispatch(fake))
    with SessionLocal.begin() as db:db.get(QueueSignal,queued).next_publish_at=utcnow()-timedelta(seconds=1)
    assert asyncio.run(broker.dispatch(fake))==1 and len(fake.messages)==1


def test_competing_publishers_claim_once(queued):
    with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(lambda _:broker.claim_signal(),range(2)))
    assert sum(row is not None for row in claims)==1


def test_reconciliation_recovers_lost_broker_state_and_old_generations_are_inert(queued):
    before=signal(queued)
    with SessionLocal.begin() as db:
        row=db.get(QueueSignal,queued);row.created_at=utcnow()-timedelta(minutes=2);row.published_at=row.created_at
    broker.reconcile();after=signal(queued)
    assert after.generation!=before.generation and not after.published_at
    assert not broker.signal_live(before.generation) and broker.signal_live(after.generation)
    with SessionLocal.begin() as db:db.delete(db.get(QueueSignal,queued))
    broker.reconcile();assert signal(queued)


def test_cancelled_source_signals_cannot_trigger_more_rendering(queued):
    row=signal(queued)
    with SessionLocal.begin() as db:db.get(RenderJob,queued).status='cancelled'
    broker.reconcile();assert not broker.signal_live(row.generation)


def test_signal_completion_requires_a_durable_job_outcome(queued):
    row=signal(queued);claimed=worker.claim_job();assert claimed['id']==queued
    assert not broker.complete_signal(row.generation,claimed)
    assert signal(queued).completed_at is None
    assert worker.mark_done(queued,claimed['claim_token'],error_code='TEST')
    assert broker.complete_signal(row.generation,claimed)
    with SessionLocal() as db:assert db.get(DeadLetter,queued).reason=='TEST'


class Pulse:
    id=str(uuid.uuid4())
    def phase(self,_):pass


def test_consumer_acknowledges_after_db_completion_and_duplicate_delivery_is_harmless(queued,monkeypatch):
    row=signal(queued);calls=[]
    def process(job):
        calls.append(job['id']);assert worker.mark_done(job['id'],job['claim_token'],error_code='TEST')
    monkeypatch.setattr(worker,'process',process)
    ctx={'job_id':'np:'+row.generation,'pulse':Pulse()}
    assert asyncio.run(broker_worker.render_next(ctx,row.generation))=='durable_outcome'
    assert asyncio.run(broker_worker.render_next(ctx,row.generation))=='stale_signal'
    assert calls==[queued]


def test_consumer_will_not_ack_unpublished_processing_result(queued,monkeypatch):
    row=signal(queued);monkeypatch.setattr(worker,'process',lambda _:None)
    with pytest.raises(Retry):asyncio.run(broker_worker.render_next({'job_id':'np:'+row.generation,'pulse':Pulse()},row.generation))
    assert signal(queued).completed_at is None


def test_shutdown_defers_delivery_without_acknowledging_or_claiming_work(queued,monkeypatch):
    row=signal(queued);monkeypatch.setattr(worker,'stop',True)
    with pytest.raises(Retry):asyncio.run(broker_worker.render_next({'job_id':'np:'+row.generation,'pulse':Pulse()},row.generation))
    assert signal(queued).completed_at is None
    with SessionLocal() as db:assert db.get(RenderJob,queued).attempt_count==0


def test_renewal_caps_at_hard_deadline_and_never_resurrects_expired_or_cancelled_claim(queued):
    claimed=worker.claim_job();assert claimed['id']==queued
    deadline=utcnow()+timedelta(seconds=20)
    with SessionLocal.begin() as db:db.get(RenderJob,queued).claim_deadline_at=deadline
    assert renew_claim(claimed)
    with SessionLocal.begin() as db:
        row=db.get(RenderJob,queued)
        assert broker.aware(row.lease_expires_at)==deadline
        row.lease_expires_at=utcnow()-timedelta(seconds=1)
    assert not renew_claim(claimed)
    assert not worker.mark_done(queued,claimed['claim_token'],error_code='LATE')
    worker.recover_stale_jobs();next_claim=worker.claim_job();assert next_claim and next_claim['claim_token']!=claimed['claim_token']
    assert not renew_claim(claimed)
    with SessionLocal.begin() as db:db.get(RenderJob,queued).status='cancelled'
    assert not renew_claim(next_claim)


def test_hard_deadline_is_enforced_even_if_lease_was_longer(queued):
    claimed=worker.claim_job()
    with SessionLocal.begin() as db:db.get(RenderJob,queued).claim_deadline_at=utcnow()-timedelta(seconds=1)
    assert not worker.owns_claim(claimed) and not renew_claim(claimed)
    assert not worker.mark_done(queued,claimed['claim_token'],error_code='LATE')
    assert worker.recover_stale_jobs()==(1,0)


def test_transient_retries_are_delayed_bounded_and_dead_lettered(queued):
    claimed=worker.claim_job()
    assert worker.mark_done(queued,claimed['claim_token'],error_code='STORAGE_UNAVAILABLE',retryable=True)
    assert worker.claim_job() is None
    with SessionLocal.begin() as db:
        row=db.get(RenderJob,queued);assert row.status=='queued' and row.next_attempt_at is not None
        row.next_attempt_at=utcnow()-timedelta(seconds=1)
    second=worker.claim_job();assert worker.mark_done(queued,second['claim_token'],error_code='STORAGE_UNAVAILABLE',retryable=True)
    with SessionLocal() as db:
        assert db.get(RenderJob,queued).status=='failed'
        assert db.get(DeadLetter,queued).attempts==2
    assert worker.claim_job() is None


def test_json_protocol_rejects_pickle_and_untrusted_functions(tmp_path):
    marker=tmp_path/'must-not-exist'
    class Payload:
        def __reduce__(self):return (open,(str(marker),'w'))
    with pytest.raises((ValueError,UnicodeError)):broker.loads(pickle.dumps(Payload()))
    assert not marker.exists()
    valid={'t':None,'f':'render_next','a':[str(uuid.uuid4())],'k':{},'et':1234}
    assert broker.loads(broker.dumps(valid))==valid
    for change in ({'f':'os.system'},{'a':['not-an-id']},{'k':{'command':'anything'}},{'extra':'forbidden'},{'t':True}):
        with pytest.raises((ValueError,TypeError)):broker.loads(broker.dumps({**valid,**change}))
    with pytest.raises(ValueError):broker.loads(b' '*5000)


def test_broker_requires_durable_configuration_and_verified_tls(monkeypatch):
    monkeypatch.setattr(get_settings(),'queue_backend','valkey')
    class Pool:
        closed=False
        async def config_get(self,*_):return {b'appendonly':b'no',b'appendfsync':b'always',b'maxmemory-policy':b'noeviction'}
        async def aclose(self):self.closed=True
    pool=Pool();captured=[]
    async def create(settings,**kwargs):captured.append(settings);return pool
    monkeypatch.setattr(broker,'create_pool',create)
    with pytest.raises(RuntimeError,match='AOF'):asyncio.run(broker.connect())
    assert pool.closed and captured[0].ssl_check_hostname is True and captured[0].ssl_cert_reqs=='required'
    monkeypatch.setenv('QUEUE_BACKEND','valkey')
    with pytest.raises(RuntimeError,match='strong'):Settings()
    monkeypatch.setenv('QUEUE_PASSWORD','synthetic-broker-password-at-least-32-characters');monkeypatch.setenv('APP_ENV','staging')
    with pytest.raises(RuntimeError,match='verified TLS'):Settings()


def test_private_queue_setup_preserves_credentials_without_echoing_them(tmp_path,monkeypatch,capsys):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('queue_setup',Path(__file__).resolve().parents[3]/'scripts/configure_queue.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'ROOT',tmp_path)
    module.main();first=json.loads((tmp_path/'.data/queue-private/client.json').read_text())
    module.main();second=json.loads((tmp_path/'.data/queue-private/client.json').read_text())
    assert first==second and len(first['QUEUE_PASSWORD'])>=32
    assert first['QUEUE_PASSWORD'] not in capsys.readouterr().out
    assert 'appendfsync always' in (tmp_path/'.data/queue-private/valkey.conf').read_text()
    if __import__('os').name=='posix':assert (tmp_path/'.data/queue-private').stat().st_mode&0o077==0


def test_live_supervision_survives_original_short_lease_without_extending_hard_deadline(queued,monkeypatch):
    import time
    monkeypatch.setattr(get_settings(),'worker_lease_seconds',15)
    monkeypatch.setattr(get_settings(),'worker_renew_seconds',1)
    claimed=worker.claim_job()
    with SessionLocal() as db:deadline=broker.aware(db.get(RenderJob,queued).claim_deadline_at)
    with ClaimSupervisor(claimed) as supervisor:
        time.sleep(16)
        assert not supervisor.lost.is_set() and worker.owns_claim(claimed)
        with SessionLocal() as db:
            row=db.get(RenderJob,queued)
            assert broker.aware(row.claim_deadline_at)==deadline and row.attempt_count==1
            assert broker.aware(row.lease_expires_at)>utcnow()


def test_deletion_preserves_lost_attempt_writer_deadline_after_short_lease(queued,client):
    from app.models import User,AccountDeletion
    claimed=worker.claim_job();deadline=utcnow()+timedelta(minutes=25)
    with SessionLocal.begin() as db:
        job=db.get(RenderJob,queued);job.claim_deadline_at=None
        db.get(RenderAttempt,claimed['claim_token']).deadline_at=deadline
        user=db.get(User,claimed['user_id']);email=user.email
    token=client.post('/api/v1/auth/login',json={'email':email,'password':'correct horse battery staple'}).json()['access_token']
    headers={'Authorization':'Bearer '+token}
    assert client.delete('/api/v1/jobs/'+queued,headers=headers).status_code==202
    with SessionLocal() as db:assert broker.aware(db.get(RenderJob,queued).cleanup_after)>=deadline
    assert client.post('/api/v1/account/delete',headers=headers,json={'current_password':'correct horse battery staple','receipt_key':str(uuid.uuid4())}).status_code==202
    with SessionLocal() as db:assert broker.aware(db.get(AccountDeletion,claimed['user_id']).cleanup_after)>=deadline
