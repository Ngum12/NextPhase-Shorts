"""Operator-imported total provider usage and fail-closed admission pause.

Not a provider billing API, invoice verification service or infrastructure kill.
"""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import tempfile
from fastapi import HTTPException

COMPONENTS={'api','worker','database','queue','storage','egress','backup','observability'}
REASONS={'ok','budget_reached','input_incomplete','operator_pause'}


def amount(value):
    if not isinstance(value,str):raise ValueError()
    result=Decimal(value)
    if not result.is_finite() or not 0<=result<=1000000:raise ValueError()
    return result


def reconcile(policy,usage,*,now=None):
    now=now or datetime.now(timezone.utc)
    if set(policy)!={'version','currency','budget_usd','approved','mode'} or policy['version']!=1 or policy['currency']!='USD' or type(policy['approved']) is not bool or policy['mode'] not in ('local_fixture','provider_export'):raise ValueError()
    budget=amount(policy['budget_usd'])
    if not budget:raise ValueError()
    if set(usage)!={'version','currency','mode','window_start','window_end','updated_at','components'} or usage['version']!=1 or usage['currency']!='USD' or usage['mode']!=policy['mode']:raise ValueError()
    start,end,updated=(datetime.fromisoformat(usage[key]) for key in ('window_start','window_end','updated_at'))
    if any(value.tzinfo is None for value in (start,end,updated)) or not start<=now<=end or not start<=updated<=now or now-updated>timedelta(hours=24):raise ValueError()
    if not set(usage['components'])<=COMPONENTS:raise ValueError()
    total=sum((amount(value) for value in usage['components'].values()),Decimal(0))
    complete=set(usage['components'])==COMPONENTS and policy['approved']
    reason='input_incomplete' if not complete else 'budget_reached' if total>=budget else 'ok'
    return {'version':1,'generated_at':now.isoformat(),'valid_until':(now+timedelta(minutes=5)).isoformat(),
        'paused':reason!='ok','reason':reason,'mode':policy['mode'],'budget_usd':str(budget),
        'provider_total_usd':str(total),'source_hash':hashlib.sha256(json.dumps(usage,sort_keys=True).encode()).hexdigest(),
        'scope':'application admission/claim gate; not provider billing stop'}


def write_state(path,state,*,allow_resume=False):
    path=Path(path)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):raise ValueError()
    if path.exists():
        previous=json.loads(path.read_bytes())
        if set(previous)!={'version','generated_at','valid_until','paused','reason','mode','budget_usd','provider_total_usd','source_hash','scope'}:raise ValueError()
        if previous.get('paused') and not state['paused'] and not allow_resume:
            state={**state,'paused':True,'reason':'operator_pause'}
    descriptor,temporary=tempfile.mkstemp(prefix='budget-',dir=path.parent)
    try:
        with os.fdopen(descriptor,'w') as handle:json.dump(state,handle);handle.flush();os.fsync(handle.fileno())
        os.replace(temporary,path)
    finally:Path(temporary).unlink(missing_ok=True)


def require_open():
    from .config import get_settings
    settings=get_settings();location=settings.budget_state_file
    if not location:
        if settings.env in ('staging','production'):raise HTTPException(503,'Operator budget controls are required',headers={'Cache-Control':'no-store'})
        return
    try:
        path=Path(location)
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):raise ValueError()
        info=path.stat()
        if info.st_nlink!=1 or (os.name=='posix' and (info.st_uid!=os.geteuid() or info.st_mode&0o077)):raise ValueError()
        with path.open('rb') as handle:data=handle.read(8193)
        if len(data)>8192:raise ValueError()
        state=json.loads(data);now=datetime.now(timezone.utc)
        if set(state)!={'version','generated_at','valid_until','paused','reason','mode','budget_usd','provider_total_usd','source_hash','scope'} or state['version']!=1 or type(state['paused']) is not bool or state['reason'] not in REASONS:raise ValueError()
        generated,expiry=datetime.fromisoformat(state['generated_at']),datetime.fromisoformat(state['valid_until'])
        if not generated<=now<expiry or expiry-generated>timedelta(minutes=5):raise ValueError()
        if state['mode'] not in ('provider_export','local_fixture') or (state['mode']=='local_fixture' and settings.env not in ('development','test')):raise ValueError()
        if amount(state['provider_total_usd'])>=amount(state['budget_usd']) or state['reason']!='ok' or state['paused']:raise ValueError()
    except Exception:
        raise HTTPException(503,'New renders are temporarily paused by operator budget controls',headers={'Retry-After':'60','Cache-Control':'no-store'}) from None


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy',type=Path,required=True);parser.add_argument('--usage',type=Path,required=True)
    parser.add_argument('--state',type=Path,required=True);parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    try:
        state=reconcile(json.loads(args.policy.read_bytes()),json.loads(args.usage.read_bytes()))
        write_state(args.state,state,allow_resume=args.resume)
        result=json.loads(args.state.read_bytes());print(json.dumps({'paused':result['paused'],'reason':result['reason'],'scope':result['scope']}))
    except Exception:parser.exit(1,'Budget reconciliation refused; existing state preserved and missing/stale state fails closed.\n')

if __name__=='__main__':main()
