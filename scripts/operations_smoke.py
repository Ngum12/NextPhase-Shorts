"""Inspect only the stopped, disposable HTTP smoke database and safe event logs."""
from datetime import timedelta
import json,os,subprocess,sys,uuid
from pathlib import Path
from sqlalchemy import select
from app.config import get_settings
from app.db import SessionLocal,engine
from app.models import WorkerPulse,RenderJob,User,utcnow
from app.operations import report


def main():
    if get_settings().env!='test' or engine.dialect.name!='sqlite' or 'nextphase-smoke-' not in str(engine.url.database):
        raise RuntimeError('Operations proof requires the disposable HTTP smoke database')
    output=Path(sys.argv[1])
    with SessionLocal() as db:
        pulses=list(db.scalars(select(WorkerPulse)))
        assert pulses and all(pulse.heartbeat_at>pulse.started_at for pulse in pulses)
        snapshot=report(db)
        if os.name!='nt':assert snapshot['workers']['stopped']>=1 and snapshot['workers']['fresh']==0
        future=report(db,now=utcnow()+timedelta(seconds=200))
        assert future['workers']['fresh']==0 and 'no_fresh_workers' in future['issues']
    uid=str(uuid.uuid4())
    with SessionLocal.begin() as db:
        db.add(User(id=uid,email=uid+'@example.com',password_hash='synthetic'));db.flush()
        db.add(RenderJob(user_id=uid,title='Synthetic stalled claim',style='vlog',desired_seconds=15,
            source_duration_seconds=5,source_path='synthetic-not-read',status='processing',
            lease_expires_at=utcnow()-timedelta(seconds=1),started_at=utcnow()-timedelta(minutes=1)))
    checked=subprocess.run([sys.executable,'-m','app.operations','--check'],capture_output=True,text=True,timeout=30)
    assert checked.returncode==1
    failed=json.loads(checked.stdout);assert failed['queue']['expired_processing_claims']==1
    events=[]
    for line in (output/'worker.log').read_text().splitlines():
        if line.startswith('{'):
            row=json.loads(line)
            if row.get('component')=='worker':events.append(row['event'])
    assert events.count('render_completed')>=2 and 'worker_started' in events
    if os.name!='nt':assert 'worker_stopped' in events
    engine.dispose()
    print(json.dumps({'live_heartbeat_advanced':True,'shutdown_stopped_records':snapshot['workers']['stopped'],
        'expired_claim_cli_exit':checked.returncode,'structured_completed_events':events.count('render_completed'),
        'missing_worker_detected':True,'clock':'advanced 200 seconds only in stopped-fixture report; no lease changed'}))


if __name__=='__main__':main()
