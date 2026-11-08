"""Measured-cost estimates, with explicit unknowns; never billing/provider invoices."""
from datetime import timezone
from decimal import Decimal,InvalidOperation
import json
from sqlalchemy import select,func,exists
from sqlalchemy.exc import SQLAlchemyError
from .models import ArtifactMeasure,RenderJob,RenderAttempt,Observation,utcnow
from .telemetry import distribution

RATE_NAMES={'worker_hour','storage_gib_day','api_egress_gib','storage_read_gib','storage_write_gib'}


def load_rates(path):
    if path is None:return None
    try:
        with open(path,'rb') as handle:data=handle.read(8193)
        if len(data)>8192:raise ValueError()
        card=json.loads(data)
        if set(card)!={'version','currency','rates'} or type(card['version']) is not int or card['version']!=1 or card['currency']!='USD':raise ValueError()
        if set(card['rates'])!=RATE_NAMES:raise ValueError()
        for key,value in card['rates'].items():
            if not isinstance(value,str):raise ValueError()
            rate=Decimal(value)
            if not rate.is_finite() or not 0<=rate<=1000000:raise ValueError()
            card['rates'][key]=rate
        return card
    except (OSError,ValueError,TypeError,InvalidOperation):
        raise ValueError('Invalid rate card; use the documented USD schema') from None


def measure_artifact(job_id,kind,size,db=None):
    if kind not in ('original','output') or type(size) is not int or size<0:raise ValueError('Invalid artifact measurement')
    row=ArtifactMeasure(job_id=job_id,kind=kind,bytes=size,stored_at=utcnow())
    if db is not None:db.add(row);return
    from .db import SessionLocal
    try:
        with SessionLocal.begin() as session:session.add(row)
    except SQLAlchemyError:
        from .observability import logger
        logger.warning('artifact_measurement_unavailable')


def aware(value):return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def report(db,*,since,now=None,limit=10000,rates=None):
    now=now or utcnow()
    if not 1<=limit<=100000 or aware(since)>=aware(now):raise ValueError('Invalid cost window')
    jobs=list(db.scalars(select(RenderJob).where(RenderJob.created_at<=now,
        (RenderJob.media_deleted_at.is_(None)) | (RenderJob.media_deleted_at>=since))
        .order_by(RenderJob.created_at,RenderJob.id).limit(limit+1)))
    attempts=list(db.scalars(select(RenderAttempt).where(RenderAttempt.started_at>=since,RenderAttempt.started_at<=now)
        .order_by(RenderAttempt.started_at,RenderAttempt.id).limit(limit+1)))
    observations=list(db.scalars(select(Observation).where(Observation.started_ns>=int(aware(since).timestamp()*1e9),
        Observation.started_ns<=int(aware(now).timestamp()*1e9)).order_by(Observation.started_ns,Observation.id).limit(limit+1)))
    artifacts=list(db.scalars(select(ArtifactMeasure).where(ArtifactMeasure.stored_at<=now)
        .order_by(ArtifactMeasure.stored_at,ArtifactMeasure.id).limit(limit+1)))
    truncated=any(len(rows)>limit for rows in (jobs,attempts,observations,artifacts))
    jobs=jobs[:limit];attempts=attempts[:limit];observations=observations[:limit];artifacts=artifacts[:limit]
    by_job={j.id:j for j in jobs};cost_by_job={};gib_days=Decimal(0);artifact_jobs=set()
    totals={key:Decimal(0) for key in RATE_NAMES};cpu=[];rss=[];stage_wall={}
    for a in attempts:
        if a.wall_seconds is not None:
            units=Decimal(str(a.wall_seconds))/Decimal(3600);totals['worker_hour']+=units
            cost_by_job.setdefault(a.job_id,{})['worker_hour']=cost_by_job.get(a.job_id,{}).get('worker_hour',Decimal(0))+units
    for a in artifacts:
        job=by_job.get(a.job_id)
        if not job:continue
        artifact_jobs.add(job.id)
        start=max(aware(a.stored_at),aware(since));end=min(aware(job.media_deleted_at or now),aware(now))
        days=Decimal(str(max(0,(end-start).total_seconds())))/Decimal(86400)
        units=Decimal(a.bytes)/Decimal(2**30)*days;gib_days+=units
        cost_by_job.setdefault(job.id,{})['storage_gib_day']=cost_by_job.get(job.id,{}).get('storage_gib_day',Decimal(0))+units
    totals['storage_gib_day']=gib_days
    ingress=0;attempt_records=set()
    for o in observations:
        from .observability import validate_fields,STAGES
        if o.stage not in STAGES:raise ValueError('Invalid stored stage')
        m=json.loads(o.attributes);validate_fields(m)
        if o.stage=='attempt':attempt_records.add(o.attempt_id)
        if o.stage=='encode':
            if 'cpu_seconds_lower_bound' in m:cpu.append(m['cpu_seconds_lower_bound'])
            if 'rss_bytes_sampled_max' in m:rss.append(m['rss_bytes_sampled_max'])
        stage_wall.setdefault(o.stage,[]).append(m.get('wall_seconds',0))
        ingress+=m.get('received_bytes',0)
        for field,rate in (('sent_bytes','api_egress_gib'),('storage_read_bytes','storage_read_gib'),('storage_write_bytes','storage_write_gib')):
            units=Decimal(m.get(field,0))/Decimal(2**30);totals[rate]+=units
            if o.job_id:cost_by_job.setdefault(o.job_id,{})[rate]=cost_by_job.get(o.job_id,{}).get(rate,Decimal(0))+units
    missing_outputs=db.scalar(select(func.count()).select_from(RenderAttempt).join(RenderJob,RenderJob.id==RenderAttempt.job_id).where(
        RenderAttempt.status=='succeeded',RenderAttempt.started_at<=now,
        (RenderJob.media_deleted_at.is_(None)) | (RenderJob.media_deleted_at>=since),
        ~exists(select(ArtifactMeasure.id).where(ArtifactMeasure.job_id==RenderAttempt.job_id,ArtifactMeasure.kind=='output')).correlate(RenderAttempt)))
    def price(units):return sum((quantity*rates['rates'][key] for key,quantity in units.items()),Decimal(0)) if rates else None
    def money(value):return str(value.quantize(Decimal('.00000001'))) if value is not None else None
    job_prices=[float(price(units)) for units in cost_by_job.values()] if rates else []
    return {'schema_version':1,'window_start':since.isoformat(),'window_end':now.isoformat(),'truncated':truncated,
        'row_limit_per_table':limit,'rates_configured':rates is not None,'currency':'USD',
        'observed_units':{key:str(value) for key,value in totals.items()},'api_received_bytes':ingress,
        'estimate_by_component':{key:money(value*rates['rates'][key]) if rates else None for key,value in totals.items()},
        'estimated_observed_total':money(price(totals)),
        'per_job_partial_estimate':distribution(job_prices),
        'stage_wall_seconds':{k:distribution(v) for k,v in stage_wall.items()},
        'decoder_cpu_seconds_lower_bound':sum(cpu),'decoder_cpu_samples':len(cpu),
        'decoder_rss_bytes_sampled_max':max(rss) if rss else None,
        'coverage':{'attempts':len(attempts),'unmeasured_wall_attempts':sum(a.wall_seconds is None for a in attempts),
            'attempts_without_spans':sum(a.id not in attempt_records for a in attempts),
            'successful_attempts_without_output_measurements':missing_outputs,
            'retained_jobs_without_artifact_measurements':sum(j.id not in artifact_jobs for j in jobs),
            'gpu':'not used by baseline; no GPU meter','ai':'not called by baseline; no AI meter',
            'unknown':['direct signed GET/PUT traffic','failed or interrupted storage transfers','staging/orphans/backups/metadata',
                'idle worker/API/database/broker compute','provider requests/taxes/discounts','unsampled decoder CPU/RSS']},
        'scope':'Partial estimate from observed wall allocation, known artifact lifetime and ASGI/storage bytes; not invoices, total spend or a hard spend cap'}
