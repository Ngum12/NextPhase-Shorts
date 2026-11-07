"""Local operator-only aggregate report. Never exports user IDs, titles or paths."""
import argparse
from collections import Counter
from datetime import timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import math
from sqlalchemy import select
from .db import SessionLocal, engine
from .migrate import require_current_schema
from .models import RenderAttempt, RenderJob, utcnow


def seconds(start, end):
    def aware(value):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return max(0.0,(aware(end)-aware(start)).total_seconds())


def distribution(values):
    values=sorted(values)
    return {'samples':len(values),
        'p50':values[math.ceil(len(values)*.50)-1] if values else None,
        'p95':values[math.ceil(len(values)*.95)-1] if values else None}


def hourly_rate(value):
    try:
        rate=Decimal(value)
        if not rate.is_finite() or not 0 <= rate <= 1000000:
            raise ValueError()
        return rate
    except (InvalidOperation, ValueError):
        raise argparse.ArgumentTypeError('Hourly rate must be finite and between 0 and 1000000')


def report(db, *, days=7, limit=10000, rate=None, currency='USD'):
    now=utcnow();since=now-timedelta(days=days)
    attempts=list(db.scalars(select(RenderAttempt).where(RenderAttempt.started_at >= since,
        RenderAttempt.started_at <= now).order_by(RenderAttempt.started_at.desc(),RenderAttempt.id).limit(limit+1)))
    jobs=list(db.scalars(select(RenderJob).where(RenderJob.created_at >= since,
        RenderJob.created_at <= now).order_by(RenderJob.created_at.desc(),RenderJob.id).limit(limit+1)))
    truncated=len(attempts)>limit or len(jobs)>limit
    attempts=attempts[:limit];jobs=jobs[:limit]
    observed=[a.wall_seconds for a in attempts if a.wall_seconds is not None]
    successful=[j for j in jobs if j.status=='succeeded' and j.finished_at]
    # Only first claims are pure queue wait; retries include earlier work/downtime.
    by_job={j.id:j for j in jobs}
    queue=[seconds(by_job[a.job_id].created_at,a.started_at) for a in attempts
           if a.number==1 and a.job_id in by_job]
    attempt_job_ids={a.job_id for a in attempts}
    measured=sum((Decimal(str(value)) for value in observed),Decimal(0))
    estimate=(measured*rate/Decimal(3600)).quantize(Decimal('0.00000001')) if rate is not None else None
    return {'schema_version':1,'generated_at':now.isoformat(),'window_days':days,'row_limit_per_table':limit,
        'truncated':truncated,'job_states':dict(Counter(j.status for j in jobs)),
        'attempt_states':dict(Counter(a.status for a in attempts)),
        'attempts':len(attempts),'retry_attempts':sum(a.number>1 for a in attempts),
        'attempt_wall_seconds':distribution(observed),
        'first_claim_queue_seconds':distribution(queue),
        'successful_job_turnaround_seconds':distribution([seconds(j.created_at,j.finished_at) for j in successful]),
        'successful_output_bytes':sum(a.output_bytes or 0 for a in attempts if a.status=='succeeded'),
        'unmeasured_attempts':sum(a.wall_seconds is None for a in attempts),
        'jobs_without_attempt_records':sum(j.id not in attempt_job_ids for j in jobs),
        'compute_estimate':{'currency':currency,'allocated_worker_hourly_rate':str(rate) if rate is not None else None,
            'observed_wall_seconds':float(measured),'amount_for_observed_attempts':str(estimate) if estimate is not None else None,
            'scope':'observed attempt wall time only; not CPU seconds, provider charges or total cost'}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days',type=int,default=7)
    parser.add_argument('--limit',type=int,default=10000)
    parser.add_argument('--hourly-rate',type=hourly_rate)
    parser.add_argument('--currency',default='USD')
    args=parser.parse_args()
    if not 1<=args.days<=365 or not 1<=args.limit<=100000:
        parser.error('Days must be 1–365 and limit 1–100000')
    if len(args.currency)!=3 or not args.currency.isascii() or not args.currency.isalpha():
        parser.error('Currency must be a three-letter code')
    require_current_schema(engine)
    with SessionLocal() as db:
        print(json.dumps(report(db,days=args.days,limit=args.limit,rate=args.hourly_rate,currency=args.currency.upper()),indent=2))


if __name__=='__main__':
    main()
