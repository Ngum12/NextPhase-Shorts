import argparse
from datetime import timedelta
from decimal import Decimal
import json
import pytest
from sqlalchemy import select
from app.db import SessionLocal
from app.models import RenderAttempt, RenderJob, utcnow
from app.telemetry import distribution, hourly_rate, report
from app.worker import claim_job, mark_done, process, recover_stale_jobs, settings
from test_worker import queued_job


def attempt(token):
    with SessionLocal() as db:return db.get(RenderAttempt,token)


def test_success_records_bytes_and_time_once(client,monkeypatch):
    job_id,_=queued_job(client,monkeypatch);job=claim_job()
    def render(source,output,duration,**kwargs):
        output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(b'rendered');return {'duration':2}
    monkeypatch.setattr('app.worker.render_baseline',render)
    process(job)
    row=attempt(job['claim_token'])
    assert row.job_id==job_id and row.number==1 and row.status=='succeeded'
    assert row.wall_seconds>=0 and row.output_bytes==8 and row.finished_at
    assert not mark_done(job_id,job['claim_token'],error_code='LATE')
    assert attempt(job['claim_token']).status=='succeeded'


def test_failure_redacts_exception_and_measures_work(client,monkeypatch,caplog):
    _,_=queued_job(client,monkeypatch);job=claim_job()
    def crash(*args,**kwargs):raise RuntimeError('secret-private-path-user-email')
    monkeypatch.setattr('app.worker.render_baseline',crash)
    process(job)
    row=attempt(job['claim_token'])
    assert row.status=='failed' and row.wall_seconds>=0 and row.output_bytes is None
    assert 'secret-private-path-user-email' not in caplog.text


def test_cancel_is_durable_even_if_worker_never_returns(client,monkeypatch):
    job_id,token=queued_job(client,monkeypatch);job=claim_job()
    response=client.post(f'/api/v1/jobs/{job_id}/cancel',headers={'Authorization':'Bearer '+token})
    assert response.status_code==200
    row=attempt(job['claim_token'])
    assert row.status=='cancelled' and row.wall_seconds is None
    process(job)
    row=attempt(job['claim_token'])
    assert row.status=='cancelled' and row.wall_seconds>=0


def test_crash_recovery_keeps_unknown_time_and_fences_retry(client,monkeypatch):
    job_id,_=queued_job(client,monkeypatch);old=claim_job()
    with SessionLocal.begin() as db:db.get(RenderJob,job_id).lease_expires_at=utcnow()-timedelta(seconds=1)
    recover_stale_jobs()
    row=attempt(old['claim_token'])
    assert row.status=='lease_lost' and row.wall_seconds is None
    new=claim_job()
    assert new['id']==job_id and new['claim_token']!=old['claim_token']
    assert attempt(new['claim_token']).number==2
    assert not mark_done(job_id,old['claim_token'],error_code='STALE')
    assert attempt(new['claim_token']).status=='running'
    mark_done(job_id,new['claim_token'],error_code='CLEANUP')


def test_report_counts_unknowns_and_estimates_only_observed_work(client,monkeypatch):
    job_id,_=queued_job(client,monkeypatch);job=claim_job()
    assert mark_done(job_id,job['claim_token'],error_code='TEST',wall_seconds=3600)
    queued_job(client,monkeypatch);unknown=claim_job()
    mark_done(unknown['id'],unknown['claim_token'],error_code='NO_MEASUREMENT')
    with SessionLocal() as db:
        result=report(db,rate=Decimal('0.25'))
        no_rate=report(db)
        truncated=report(db,limit=1)
    assert result['attempt_wall_seconds']['samples']>=1
    assert Decimal(result['compute_estimate']['amount_for_observed_attempts'])>=Decimal('.25')
    expected=(Decimal(str(result['compute_estimate']['observed_wall_seconds']))*Decimal('.25')/3600).quantize(Decimal('.00000001'))
    assert Decimal(result['compute_estimate']['amount_for_observed_attempts'])==expected
    assert result['unmeasured_attempts']>=1
    assert no_rate['compute_estimate']['amount_for_observed_attempts'] is None
    assert truncated['truncated']
    encoded=json.dumps(result)
    for private in (job_id,job['claim_token'],job['source'],job['user_id']):assert private not in encoded


@pytest.mark.parametrize('value',['NaN','Infinity','-1','1000001','invalid'])
def test_invalid_rate_rejected(value):
    with pytest.raises(argparse.ArgumentTypeError):hourly_rate(value)


def test_distributions_have_explicit_sample_sizes_and_nearest_rank():
    assert distribution([])=={'samples':0,'p50':None,'p95':None}
    assert distribution(range(1,21))=={'samples':20,'p50':10,'p95':19}
    assert hourly_rate('0')==0


def test_empty_report_does_not_invent_samples_or_free_compute():
    from unittest.mock import Mock
    db=Mock();db.scalars.return_value=[]
    result=report(db)
    assert result['attempt_wall_seconds']['samples']==0
    assert result['successful_job_turnaround_seconds']['p95'] is None
    assert result['compute_estimate']['amount_for_observed_attempts'] is None
    assert not result['truncated']
