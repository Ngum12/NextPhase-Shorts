"""Operator reports and process liveness, not user/public metrics endpoints."""
from datetime import timedelta
import json,time,uuid
from pathlib import Path
import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from app.migrate import upgrade_schema
from app.models import User,RenderJob,WorkerPulse,utcnow
from app.operations import report
from app.worker_health import WorkerHeartbeat
from app.worker_events import emit
from test_migrations import migration_engine


@pytest.fixture
def ops(migration_engine,monkeypatch):
    upgrade_schema(migration_engine)
    factory=sessionmaker(bind=migration_engine,expire_on_commit=False)
    monkeypatch.setattr('app.worker_health.SessionLocal',factory)
    yield factory


def add_job(db,status,now,**overrides):
    uid=str(uuid.uuid4());db.add(User(id=uid,email=uid+'@example.com',password_hash='private-password'));db.flush()
    values=dict(id=str(uuid.uuid4()),user_id=uid,title='private-title',style='vlog',desired_seconds=15,
        source_duration_seconds=5,source_path='/private/customer/source.mp4',status=status,created_at=now-timedelta(minutes=10))
    values.update(overrides);job=RenderJob(**values);db.add(job);db.flush();return job


def pulse(db,now,*,age=0,phase='idle',stopped=False,interval=10):
    row=WorkerPulse(id=str(uuid.uuid4()),started_at=now-timedelta(hours=1),heartbeat_at=now-timedelta(seconds=age),
        phase=phase,heartbeat_seconds=interval,stopped_at=now if stopped else None)
    db.add(row);db.flush();return row


def test_snapshot_backlog_expired_claims_and_failures_are_private(ops):
    now=utcnow()
    with ops.begin() as db:
        add_job(db,'queued',now)
        add_job(db,'processing',now,started_at=now-timedelta(minutes=2),lease_expires_at=now-timedelta(seconds=1))
        add_job(db,'processing',now,started_at=now-timedelta(seconds=30))
        add_job(db,'failed',now,finished_at=now,error_code='RENDER_FAILED')
        add_job(db,'failed',now,finished_at=now,error_code='private-path-and-email@example.com')
        add_job(db,'deleted',now)
        pulse(db,now)
    with ops() as db:result=report(db,now=now)
    assert result['job_states']=={'queued':1,'processing':2,'failed':2}
    assert result['queue']=={'oldest_queued_seconds':600,'oldest_processing_seconds':120,
        'expired_processing_claims':1,'missing_processing_deadlines':1}
    assert result['failed_job_codes_finished_in_window']=={'RENDER_FAILED':1,'other':1}
    assert result['status']=='attention_required' and 'expired_processing_claims' in result['issues']
    serialized=json.dumps(result)
    for secret in ('private','example.com','source.mp4','user_id','job_id'):assert secret not in serialized


def test_fresh_stale_stopped_future_and_old_worker_states(ops):
    now=utcnow()
    with ops.begin() as db:
        pulse(db,now);pulse(db,now,age=46);pulse(db,now,stopped=True,phase='stopped')
        pulse(db,now,age=-30);pulse(db,now,age=90000)
    with ops() as db:result=report(db,now=now)
    assert {key:result['workers'][key] for key in ('observed','fresh','stale','stopped','clock_skew')}=={
        'observed':4,'fresh':1,'stale':1,'stopped':1,'clock_skew':1}
    assert result['issues']==['worker_clock_skew']


def test_truncated_worker_inventory_is_not_claimed_healthy(ops):
    now=utcnow()
    with ops.begin() as db:pulse(db,now);pulse(db,now)
    with ops() as db:result=report(db,now=now,worker_limit=1)
    assert result['workers']['truncated'] and 'worker_inventory_truncated' in result['issues']


def test_no_worker_is_visible_even_for_an_empty_queue(ops):
    with ops() as db:result=report(db)
    assert result['issues']==['no_fresh_workers'] and result['queue']['oldest_queued_seconds'] is None


def test_heartbeat_runs_during_foreground_work_and_never_renews_lease(ops):
    with ops.begin() as db:
        job=add_job(db,'processing',utcnow(),lease_expires_at=utcnow()+timedelta(seconds=120));jid=job.id
        original=job.lease_expires_at
    with WorkerHeartbeat(.05) as heartbeat:
        heartbeat.phase('rendering')
        with ops() as db:first=db.get(WorkerPulse,heartbeat.id).heartbeat_at
        deadline=time.monotonic()+5
        while True:
            with ops() as db:
                row=db.get(WorkerPulse,heartbeat.id)
                if row.heartbeat_at>first and row.phase=='rendering':break
            assert time.monotonic()<deadline
            time.sleep(.02)
        with ops() as db:
            # SQLite loses tzinfo; compare wall values, not an artificial timezone shift.
            assert db.get(RenderJob,jid).lease_expires_at.replace(tzinfo=None)==original.replace(tzinfo=None)
    with ops() as db:
        row=db.get(WorkerPulse,heartbeat.id);assert row.stopped_at and row.phase=='stopped'
    assert not heartbeat._thread.is_alive()


def test_heartbeat_recovers_after_db_failure_without_logging_secrets(ops,monkeypatch,caplog):
    with WorkerHeartbeat(60) as heartbeat:
        with monkeypatch.context() as patch:
            def unavailable():raise OperationalError('private-url-and-password',{},Exception('secret'))
            patch.setattr('app.worker_health.SessionLocal.begin',unavailable)
            assert heartbeat.beat() is False
        assert heartbeat.beat() is True
    assert 'private-url-and-password' not in caplog.text and 'secret' not in caplog.text


def test_late_heartbeat_cannot_resurrect_stopped_record(ops):
    with WorkerHeartbeat(60) as heartbeat:pass
    heartbeat.phase('rendering');assert heartbeat.beat()
    with ops() as db:
        row=db.get(WorkerPulse,heartbeat.id);assert row.phase=='stopped' and row.stopped_at


def test_worker_events_are_structured_and_reject_private_fields(caplog):
    import logging
    caplog.set_level(logging.INFO,logger='nextphase.worker')
    jid=str(uuid.uuid4());emit('render_completed',job_id=jid,output_seconds=4.9)
    row=json.loads(caplog.records[-1].message)
    assert row['event']=='render_completed' and row['job_id']==jid and row['output_seconds']==4.9
    assert row['schema_version']==1 and row['timestamp']
    count=len(caplog.records)
    for field in ('url','token','user_id','title','exception'):
        with pytest.raises(ValueError):emit('render_internal_error',**{field:'private-secret'})
    assert len(caplog.records)==count and 'private-secret' not in caplog.text


def test_event_error_does_not_capture_current_exception(caplog):
    try:raise RuntimeError('private-source-and-token')
    except RuntimeError:emit('render_internal_error')
    assert 'private-source-and-token' not in caplog.text
    assert caplog.records[-1].exc_info is None


def test_readiness_is_minimal_no_store_and_preserves_liveness(client,monkeypatch):
    assert client.get('/ready').json()=={'ok':True,'service':'nextphase-shorts'}
    for exception in (RuntimeError,OperationalError):
        def unavailable(*args):
            if exception is OperationalError:raise OperationalError('secret-database',{},Exception('private'))
            raise exception('private-schema')
        monkeypatch.setattr('app.main.require_current_schema',unavailable)
        response=client.get('/ready')
        assert response.status_code==503 and response.json()=={'ok':False,'service':'nextphase-shorts'}
        assert response.headers['cache-control']=='no-store'
        assert 'private' not in response.text and 'secret' not in response.text
        assert client.get('/health').json()['ok'] is True
    for route in ('/metrics','/api/v1/operations','/api/v1/workers'):assert client.get(route).status_code==404


def test_cli_unavailable_error_is_sanitized(monkeypatch,capsys):
    import app.operations as operations
    monkeypatch.setattr('sys.argv',['operations','--check'])
    def unavailable(_):raise RuntimeError('private-db-path')
    monkeypatch.setattr(operations,'require_current_schema',unavailable)
    with pytest.raises(SystemExit) as stopped:operations.main()
    assert stopped.value.code==2
    output=capsys.readouterr();assert json.loads(output.out)['status']=='unavailable' and 'private' not in output.out


def test_cli_attention_check_returns_nonzero_without_mutation(ops,monkeypatch,capsys):
    import app.operations as operations
    monkeypatch.setattr('sys.argv',['operations','--check'])
    monkeypatch.setattr(operations,'require_current_schema',lambda _:None)
    monkeypatch.setattr(operations,'SessionLocal',ops)
    with pytest.raises(SystemExit) as stopped:operations.main()
    assert stopped.value.code==1 and json.loads(capsys.readouterr().out)['issues']==['no_fresh_workers']
