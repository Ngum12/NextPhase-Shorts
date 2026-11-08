from datetime import timedelta
from decimal import Decimal
import json
import logging
import os
from pathlib import Path
import re
import pytest
from sqlalchemy import select,create_engine
from sqlalchemy.orm import Session
from app.db import Base,SessionLocal
from app.models import ArtifactMeasure,Observation,RenderAttempt,RenderJob,User,utcnow
from app.observability import Recorder,current,stage,save,otlp,export,validate_fields
from app.costs import load_rates,report,RATE_NAMES
from app.monitoring import snapshot,prometheus
from app.secret_config import read_secret,sources
from app.worker import claim_job,process
from test_worker import queued_job


@pytest.fixture
def isolated(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'metrics.db'))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_request_to_worker_trace_and_real_decoder_samples(client,tmp_path):
    from test_api import new_user
    from upload_fixtures import RIGHTS_FORM
    import subprocess
    source=tmp_path/'sample.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=30',
        '-t','2','-c:v','libx264',str(source)],check=True,timeout=30)
    token=new_user(client)
    result=client.post('/api/v1/jobs',headers={'Authorization':'Bearer '+token},
        files={'file':('sample.mp4',source.read_bytes(),'video/mp4')},data=RIGHTS_FORM)
    assert result.status_code==201
    job_id=result.json()['id']
    with SessionLocal() as db:
        job=db.get(RenderJob,job_id)
        assert re.fullmatch('[0-9a-f]{32}',job.trace_id)
        incoming=list(db.scalars(select(Observation).where(Observation.job_id==job_id)))
        assert incoming and incoming[-1].id==job.parent_span_id
        original=db.scalar(select(ArtifactMeasure).where(ArtifactMeasure.job_id==job_id))
        assert original.bytes>0
    process(claim_job())
    downloaded=client.get(f'/api/v1/jobs/{job_id}/download',headers={'Authorization':'Bearer '+token,'traceparent':'secret-malicious-value'})
    assert downloaded.status_code==200 and downloaded.headers['x-trace-id']==job.trace_id
    with SessionLocal() as db:
        spans=list(db.scalars(select(Observation).where(Observation.job_id==job_id)))
        stages={row.stage for row in spans};assert {'attempt','source_probe','encode','output_probe','http_download'}<=stages
        encoder=next(row for row in spans if row.stage=='encode');attrs=json.loads(encoder.attributes)
        if Path('/proc/self/stat').exists():assert attrs['rss_bytes_sampled_max']>0 and attrs['cpu_seconds_lower_bound']>=0
        body=next(row for row in spans if row.stage=='http_download')
        assert json.loads(body.attributes)['sent_bytes']==len(downloaded.content)
        assert len(list(db.scalars(select(ArtifactMeasure).where(ArtifactMeasure.job_id==job_id))))==2
        encoded=json.dumps(otlp(spans))
        for private in (job.title,job.source_path,job.user_id,token,'secret-malicious-value'):assert private not in encoded
        assert {row.trace_id for row in spans}=={job.trace_id}


def test_stage_failure_has_no_exception_payload_and_parent_is_restored():
    recorder=Recorder();token=current.set(recorder)
    try:
        with pytest.raises(RuntimeError):
            with stage('attempt'):
                with stage('encode'):raise RuntimeError('private-secret-contents')
    finally:current.reset(token)
    assert recorder.parent_id is None
    assert len(recorder.rows)==2 and all(r['outcome']=='error' for r in recorder.rows)
    assert recorder.rows[0]['parent_id']==recorder.rows[1]['id']
    assert 'private-secret-contents' not in json.dumps(recorder.rows)


@pytest.mark.parametrize('fields',[{'url':'private'},{'sent_bytes':float('nan')},{'sent_bytes':-1},{'sent_bytes':True},{'io_complete':'true'}])
def test_untrusted_observation_fields_are_rejected(fields):
    with pytest.raises(ValueError):validate_fields(fields)


def test_observation_loss_is_visible_without_breaking_completed_job(monkeypatch,caplog):
    from sqlalchemy.exc import OperationalError
    def unavailable():raise OperationalError('secret-path',{},Exception('secret-key'))
    from unittest.mock import Mock
    monkeypatch.setattr('app.db.SessionLocal',Mock(begin=unavailable))
    with caplog.at_level(logging.WARNING):assert not save(Recorder(rows=[{'id':'not-used'}]))
    assert 'observation_write_unavailable' in caplog.text and 'secret-key' not in caplog.text and 'secret-path' not in caplog.text


def test_export_refuses_truncated_and_unsafe_stored_attributes(isolated):
    for n in range(2):
        isolated.add(Observation(id=f'{n+1:016x}',trace_id='a'*32,stage='encode',started_ns=n+1,ended_ns=n+2,
            outcome='ok',attributes='{"wall_seconds":1}'))
    isolated.commit()
    with pytest.raises(ValueError,match='truncated'):export(isolated,limit=1)
    payload=export(isolated,limit=2)
    span=payload['resourceSpans'][0]['scopeSpans'][0]['spans'][0]
    assert span['traceId']=='a'*32 and span['startTimeUnixNano']=='1'
    first=isolated.get(Observation,'0000000000000001');first.attributes='{"user":"private"}'
    with pytest.raises(ValueError):otlp([first])


def test_exact_cost_math_storage_cleanup_and_transfer_coverage(isolated):
    now=utcnow();start=now-timedelta(days=2)
    isolated.add(User(id='owner',email='private@example.com',password_hash='hash'));isolated.flush()
    isolated.add(RenderJob(id='job',user_id='owner',title='private title',style='vlog',desired_seconds=15,
        source_duration_seconds=5,source_path='private path',status='deleted',created_at=start,
        media_deleted_at=now-timedelta(days=1)));isolated.flush()
    isolated.add(ArtifactMeasure(job_id='job',kind='original',bytes=2**30,stored_at=start))
    isolated.add(RenderAttempt(id='attempt',job_id='job',number=1,started_at=start+timedelta(seconds=1),status='succeeded',wall_seconds=3600))
    isolated.add(Observation(id='a'*16,trace_id='b'*32,job_id='job',stage='http_download',started_ns=int(start.timestamp()*1e9)+100,
        ended_ns=int(start.timestamp()*1e9)+200,outcome='ok',attributes=json.dumps({'sent_bytes':2**30,'received_bytes':12})))
    isolated.commit()
    rates={'version':1,'currency':'USD','rates':{name:Decimal('1') for name in RATE_NAMES}}
    result=report(isolated,since=start,now=now,rates=rates)
    assert Decimal(result['observed_units']['worker_hour'])==1
    assert Decimal(result['observed_units']['storage_gib_day'])==1
    assert result['estimated_observed_total']=='3.00000000'
    assert result['api_received_bytes']==12 and result['coverage']['attempts_without_spans']==1
    assert report(isolated,since=start,now=now)['estimated_observed_total'] is None
    assert report(isolated,since=start,now=now,limit=1)['truncated'] is False
    for private in ('private title','private path','private@example.com','owner'):assert private not in json.dumps(result)


@pytest.mark.parametrize('rate',['NaN','Infinity','-1',1])
def test_rate_cards_never_assume_invalid_or_free_prices(tmp_path,rate):
    path=tmp_path/'rates.json';path.write_text(json.dumps({'version':1,'currency':'USD','rates':{k:rate for k in RATE_NAMES}}))
    with pytest.raises(ValueError):load_rates(path)


def test_monitor_thresholds_and_metrics_have_no_arbitrary_labels(isolated):
    result=snapshot(isolated,ceiling=Decimal('1'))
    assert {'no_fresh_workers','cost_rates_missing'}<=set(result['issues'])
    text=prometheus(result)
    assert 'nextphase_monitor_attention 1' in text and 'estimated_observed_usd' not in text
    result['costs']['stage_wall_seconds']['private-path']={'samples':1,'p50':1,'p95':1}
    assert 'private-path' not in prometheus(result)


def test_secret_file_adapter_redacts_errors_preserves_environment_and_reports_sources(tmp_path,monkeypatch):
    path=tmp_path/'secret';path.write_text('new-private-secret\n');path.chmod(0o600)
    monkeypatch.delenv('QUEUE_PASSWORD',raising=False);monkeypatch.setenv('QUEUE_PASSWORD_FILE',str(path))
    assert read_secret('QUEUE_PASSWORD')=='new-private-secret'
    assert os.getenv('QUEUE_PASSWORD') is None and sources()['QUEUE_PASSWORD']=='file'
    monkeypatch.setenv('QUEUE_PASSWORD','private-old-value')
    with pytest.raises(RuntimeError,match='either'):read_secret('QUEUE_PASSWORD')
    monkeypatch.delenv('QUEUE_PASSWORD');path.unlink()
    with pytest.raises(RuntimeError) as error:read_secret('QUEUE_PASSWORD')
    assert str(path) not in str(error.value) and 'private' not in str(error.value)


def test_secret_file_links_permissions_and_oversize_fail_closed(tmp_path,monkeypatch):
    original=tmp_path/'original';original.write_text('s'*16385);original.chmod(0o600)
    monkeypatch.delenv('QUEUE_PASSWORD',raising=False);monkeypatch.setenv('QUEUE_PASSWORD_FILE',str(original))
    with pytest.raises(RuntimeError):read_secret('QUEUE_PASSWORD')
    original.write_text('secret')
    if os.name=='posix':
        original.chmod(0o644)
        with pytest.raises(RuntimeError):read_secret('QUEUE_PASSWORD')
        original.chmod(0o600)
    link=tmp_path/'link'
    try:link.symlink_to(original)
    except OSError:pytest.skip('Host cannot create symlinks')
    monkeypatch.setenv('QUEUE_PASSWORD_FILE',str(link))
    with pytest.raises(RuntimeError):read_secret('QUEUE_PASSWORD')


def test_api_request_logs_and_errors_omit_query_headers_and_exception_text(caplog):
    import anyio
    from app.observability import TraceMiddleware
    async def failed(scope,receive,send):raise RuntimeError('private-media-and-token')
    messages=[]
    async def send(message):messages.append(message)
    async def receive():return {'type':'http.request','body':b'private-upload'}
    async def run():
        await TraceMiddleware(failed)({'type':'http','path':'/private-email','query_string':b'token=private-secret',
            'headers':[(b'authorization',b'Bearer private-token')]},receive,send)
    with caplog.at_level(logging.INFO):anyio.run(run)
    assert messages[0]['status']==500
    assert 'request_internal_error' in caplog.text and 'request_completed' in caplog.text
    for value in ('private-secret','private-media-and-token','private-upload','private-email','private-token'):
        assert value not in caplog.text and value not in repr(messages)


def test_secret_file_rotation_requires_new_settings_and_invalidates_old_access(client,monkeypatch):
    from test_api import new_user
    from app.config import get_settings
    token=new_user(client);headers={'Authorization':'Bearer '+token}
    account=client.get('/api/v1/me',headers=headers).json()['id']
    monkeypatch.setattr(get_settings(),'jwt_secret','different-synthetic-rotation-secret-with-32-characters')
    assert client.get('/api/v1/me',headers=headers).status_code==401
    with SessionLocal() as db:assert db.get(User,account) is not None


def test_cost_alert_and_inventory_truncation_are_explicit(isolated):
    now=utcnow()
    isolated.add(User(id='u',email='u@example.com',password_hash='h'));isolated.flush()
    for n in range(2):
        isolated.add(RenderJob(id=str(n),user_id='u',title='hidden',style='vlog',desired_seconds=15,
            source_duration_seconds=5,source_path='hidden',status='succeeded'))
    isolated.flush()
    isolated.add(RenderAttempt(id='a',job_id='0',number=1,started_at=now-timedelta(seconds=2),status='succeeded',wall_seconds=3600))
    isolated.commit()
    rates={'version':1,'currency':'USD','rates':{k:Decimal('1') for k in RATE_NAMES}}
    result=snapshot(isolated,rates=rates,ceiling=Decimal('.50'),limit=1)
    assert {'observed_cost_threshold','measurement_inventory_truncated','cost_coverage_incomplete'}<=set(result['issues'])
    assert 'nextphase_estimated_observed_usd 1.00000000' in prometheus(result)


def test_background_error_after_response_does_not_send_a_second_final_body():
    import anyio
    from app.observability import TraceMiddleware
    messages=[]
    async def responded(scope,receive,send):
        await send({'type':'http.response.start','status':200,'headers':[]})
        await send({'type':'http.response.body','body':b'ok'})
        raise RuntimeError('private-background-error')
    async def send(message):messages.append(message)
    async def receive():return {'type':'http.request','body':b''}
    async def run():await TraceMiddleware(responded)({'type':'http'},receive,send)
    anyio.run(run)
    assert len(messages)==2 and messages[-1]['body']==b'ok'
