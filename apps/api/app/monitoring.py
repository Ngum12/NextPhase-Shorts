"""Private local monitor/export CLI. No network exporter or automatic paid integration."""
import argparse
from datetime import timedelta
from decimal import Decimal,InvalidOperation
import json
import os
from pathlib import Path
from sqlalchemy.exc import SQLAlchemyError
from .db import engine,SessionLocal
from .migrate import require_current_schema
from .models import utcnow
from . import costs,operations
from .observability import export
from .secret_config import sources


def snapshot(db,*,hours=24,rates=None,ceiling=None,queue_age=300,failures=5,limit=10000):
    now=utcnow();ops=operations.report(db,hours=min(hours,168),now=now)
    usage=costs.report(db,since=now-timedelta(hours=hours),now=now,rates=rates,limit=limit)
    from .capacity import report as capacity_report
    capacity=capacity_report(db)
    issues=list(ops['issues'])
    if capacity['stale_ingress_reservations']:issues.append('stale_ingress_reservations')
    if capacity['disk']!='ok':issues.append('local_disk_low_or_unavailable')
    if capacity['unknown_records']:issues.append('global_storage_inventory_unknown')
    if (ops['queue']['oldest_queued_seconds'] or 0)>queue_age:issues.append('queue_wait_threshold')
    if sum(ops['failed_job_codes_finished_in_window'].values())>=failures:issues.append('render_failure_threshold')
    if usage['truncated']:issues.append('measurement_inventory_truncated')
    if ceiling is not None:
        if not rates:issues.append('cost_rates_missing')
        elif Decimal(usage['estimated_observed_total'])>=ceiling:issues.append('observed_cost_threshold')
        if any(usage['coverage'][k] for k in ('unmeasured_wall_attempts','attempts_without_spans','retained_jobs_without_artifact_measurements','successful_attempts_without_output_measurements')):
            issues.append('cost_coverage_incomplete')
    return {'schema_version':1,'status':'attention_required' if issues else 'ok','issues':issues,
        'operations':ops,'capacity':capacity,'costs':usage,'secret_sources':sources(),
        'alerts':'local evaluation only; schedule --check and route exit codes with your approved operator tooling',
        'cost_ceiling_scope':'alert on observed partial window estimate only, never a provider billing stop'}


def prometheus(snapshot):
    ops=snapshot['operations'];cost=snapshot['costs']
    lines=['# TYPE nextphase_monitor_attention gauge',f"nextphase_monitor_attention {int(snapshot['status']!='ok')}"]
    values={'workers_fresh':ops['workers']['fresh'],'claims_expired':ops['queue']['expired_processing_claims'],
        'queue_wait_seconds':ops['queue']['oldest_queued_seconds'] or 0,'measurement_truncated':int(cost['truncated']),
        'decoder_cpu_seconds_lower_bound':cost['decoder_cpu_seconds_lower_bound'],
        'observed_api_received_bytes':cost['api_received_bytes']}
    if cost['estimated_observed_total'] is not None:values['estimated_observed_usd']=cost['estimated_observed_total']
    for name,value in values.items():lines.extend([f'# TYPE nextphase_{name} gauge',f'nextphase_{name} {value}'])
    # Fixed allowlist; no IDs/paths or arbitrary labels in metrics.
    from .observability import STAGES
    for stage,summary in sorted(cost['stage_wall_seconds'].items()):
        if stage not in STAGES:continue
        lines.append(f'nextphase_stage_samples{{stage="{stage}"}} {summary["samples"]}')
        for quantile in ('p50','p95'):
            if summary[quantile] is not None:lines.append(f'nextphase_stage_wall_seconds{{stage="{stage}",quantile="{0.5 if quantile=='p50' else 0.95}"}} {summary[quantile]}')
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hours',type=int,default=24)
    parser.add_argument('--limit',type=int,default=10000)
    parser.add_argument('--rates',help='Operator-owned JSON rate card; never activates billing')
    parser.add_argument('--cost-alert-usd')
    parser.add_argument('--queue-age-seconds',type=int,default=300)
    parser.add_argument('--failure-count',type=int,default=5)
    parser.add_argument('--format',choices=('json','prometheus','otlp'),default='json')
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--output',help='Create a new private UTF-8 export file; refuses overwrite')
    args=parser.parse_args()
    try:
        if not 1<=args.hours<=744 or not 1<=args.limit<=10000 or not 1<=args.queue_age_seconds<=86400 or not 1<=args.failure_count<=10000:raise ValueError()
        ceiling=Decimal(args.cost_alert_usd) if args.cost_alert_usd is not None else None
        if ceiling is not None and (not ceiling.is_finite() or not 0<ceiling<=1000000):raise ValueError()
        rates=costs.load_rates(args.rates)
    except (ValueError,InvalidOperation):parser.error('Invalid monitoring bounds or rate card')
    try:
        require_current_schema(engine)
        with SessionLocal() as db:
            result=snapshot(db,hours=args.hours,rates=rates,ceiling=ceiling,queue_age=args.queue_age_seconds,failures=args.failure_count,limit=args.limit)
            payload=export(db,limit=args.limit,since_ns=int((utcnow()-timedelta(hours=args.hours)).timestamp()*1e9)) if args.format=='otlp' else result
        text=prometheus(result) if args.format=='prometheus' else json.dumps(payload,indent=2)
        if args.output:
            # Create-only private output: do not replace an existing secret or follow a symlink.
            descriptor=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(descriptor,'w',encoding='utf-8') as handle:handle.write(text+'\n')
            print(json.dumps({'schema_version':1,'export_written':True,'format':args.format}))
        else:print(text)
    except (SQLAlchemyError,RuntimeError,ValueError,OSError):
        print(json.dumps({'schema_version':1,'status':'unavailable','issues':['monitoring_unavailable']}));raise SystemExit(2)
    if args.check and result['status']!='ok':raise SystemExit(1)

if __name__=='__main__':main()
