"""Operator-only aggregate snapshot; not a public endpoint or billing metric."""
import argparse
from collections import Counter
from datetime import timedelta,timezone
import json
from sqlalchemy import func,select
from sqlalchemy.exc import SQLAlchemyError
from .db import SessionLocal,engine
from .migrate import require_current_schema
from .models import RenderJob,RenderAttempt,WorkerPulse,utcnow
from .telemetry import seconds
from .worker_events import PHASES

JOB_STATES={'queued','processing','succeeded','failed','cancelled'}
ATTEMPT_STATES={'running','succeeded','failed','cancelled','lease_lost'}
ERROR_CODES={'RENDER_DEADLINE_EXCEEDED','MAX_RETRIES','RENDER_FAILED','STORAGE_UNAVAILABLE','OUTPUT_LIMIT_EXCEEDED','INTERNAL_ERROR'}


def aware(value):return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
def grouped(rows,allowed):
    result=Counter()
    for label,count in rows:result[label if label in allowed else 'other']+=count
    return dict(result)


def report(db,*,hours=24,worker_limit=1000,now=None):
    if not 1<=hours<=168 or not 1<=worker_limit<=10000:raise ValueError('Invalid operations window or worker limit')
    now=now or utcnow();since=now-timedelta(hours=hours)
    job_states=grouped(db.execute(select(RenderJob.status,func.count()).where(RenderJob.status!='deleted')
        .group_by(RenderJob.status)),JOB_STATES)
    expired=db.scalar(select(func.count()).select_from(RenderJob).where(RenderJob.status=='processing',RenderJob.lease_expires_at<=now))
    missing=db.scalar(select(func.count()).select_from(RenderJob).where(RenderJob.status=='processing',RenderJob.lease_expires_at.is_(None)))
    def oldest(state,column):
        value=db.scalar(select(func.min(column)).where(RenderJob.status==state))
        return seconds(value,now) if value else None
    attempts=grouped(db.execute(select(RenderAttempt.status,func.count()).where(
        RenderAttempt.started_at>=since,RenderAttempt.started_at<=now).group_by(RenderAttempt.status)),ATTEMPT_STATES)
    failures=grouped(db.execute(select(RenderJob.error_code,func.count()).where(RenderJob.status=='failed',
        RenderJob.finished_at>=since,RenderJob.finished_at<=now).group_by(RenderJob.error_code)),ERROR_CODES)
    pulses=list(db.scalars(select(WorkerPulse).where(WorkerPulse.heartbeat_at>=since)
        .order_by(WorkerPulse.heartbeat_at.desc(),WorkerPulse.id).limit(worker_limit+1)))
    truncated=len(pulses)>worker_limit;pulses=pulses[:worker_limit]
    fresh=stale=stopped=skew=0;phases=Counter()
    for pulse in pulses:
        phase=pulse.phase if pulse.phase in PHASES else 'other';phases[phase]+=1
        if aware(pulse.heartbeat_at)>aware(now)+timedelta(seconds=5):skew+=1;continue
        if pulse.stopped_at is not None:stopped+=1;continue
        interval=pulse.heartbeat_seconds
        # Invalid persisted intervals are not proof of liveness.
        if not 0<interval<=60:stale+=1;continue
        if seconds(pulse.heartbeat_at,now)<=interval*3+15:fresh+=1
        else:stale+=1
    issues=[]
    if not fresh:issues.append('no_fresh_workers')
    if expired:issues.append('expired_processing_claims')
    if missing:issues.append('missing_processing_deadlines')
    if skew:issues.append('worker_clock_skew')
    if truncated:issues.append('worker_inventory_truncated')
    return {'schema_version':1,'generated_at':now.isoformat(),'status':'attention_required' if issues else 'ok',
        'issues':issues,'window_hours':hours,'job_states':job_states,
        'queue':{'oldest_queued_seconds':oldest('queued',RenderJob.created_at),
            'oldest_processing_seconds':oldest('processing',RenderJob.started_at),
            'expired_processing_claims':expired,'missing_processing_deadlines':missing},
        'attempt_states_started_in_window':attempts,'failed_job_codes_finished_in_window':failures,
        'workers':{'observed':len(pulses),'fresh':fresh,'stale':stale,'stopped':stopped,'clock_skew':skew,
            'phase_counts':dict(phases),'row_limit':worker_limit,'truncated':truncated},
        'scope':'operator snapshot; liveness is not render progress, lease renewal or provider cost'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hours',type=int,default=24)
    parser.add_argument('--worker-limit',type=int,default=1000)
    parser.add_argument('--check',action='store_true',help='Exit 1 if the snapshot needs attention; exit 2 if unavailable')
    args=parser.parse_args()
    if not 1<=args.hours<=168 or not 1<=args.worker_limit<=10000:parser.error('Hours must be 1–168; worker limit 1–10000')
    try:
        require_current_schema(engine)
        with SessionLocal() as db:result=report(db,hours=args.hours,worker_limit=args.worker_limit)
    except (SQLAlchemyError,RuntimeError):
        print(json.dumps({'schema_version':1,'status':'unavailable','issues':['database_or_schema_unavailable']}))
        raise SystemExit(2)
    print(json.dumps(result,indent=2))
    if args.check and result['status']!='ok':raise SystemExit(1)


if __name__=='__main__':main()
