"""Internal synthetic offline fixture; called only after smoke-owned writers stop."""
import json
import os
from pathlib import Path
import uuid
import subprocess
import sys
from datetime import timedelta
from app.config import get_settings
from app.db import SessionLocal,engine
from app.migrate import require_current_schema
from app.models import User,RenderJob,utcnow
from app import retention
from app import object_store as store


def main():
    settings=get_settings()
    if settings.env!='test' or engine.dialect.name!='sqlite' or 'nextphase-smoke-' not in str(engine.url.database):
        raise RuntimeError('Retention smoke requires the disposable SQLite smoke DB')
    require_current_schema(engine)
    # Exercise the actual operator CLI without a clock override: fresh fixtures
    # have no eligible old files, and apply without offline must be refused.
    command=[sys.executable,'-m','app.retention','--backend','local']
    cli=json.loads(subprocess.check_output(command,text=True,timeout=30))
    assert cli['candidate_groups']==0 and not cli['truncated']
    refused=subprocess.run(command+['--apply','--expect-digest',cli['digest']],capture_output=True,text=True,timeout=30)
    assert refused.returncode==2
    accepted=json.loads(subprocess.check_output(command+['--apply','--offline','--expect-digest',cli['digest']],text=True,timeout=30))
    assert accepted['removed_groups']==0 and accepted['failed_groups']==0
    owner=str(uuid.uuid4());orphan=str(uuid.uuid4());known=str(uuid.uuid4());now=utcnow()+timedelta(days=2)
    with SessionLocal.begin() as db:
        db.add(User(id=owner,email=owner+'@example.com',password_hash='synthetic'))
        db.flush()
        db.add(RenderJob(id=known,user_id=owner,title='Protected synthetic',style='vlog',desired_seconds=15,
            source_duration_seconds=2,source_path='synthetic',status='succeeded'))
    for entity in (orphan,known):
        directory=settings.storage_dir/owner/entity;directory.mkdir(parents=True)
        (directory/'input.mp4').write_bytes(b'synthetic retention fixture')
    plan=retention.preview(now=now)
    assert plan['candidate_groups']>=1 and not plan['truncated']
    assert (settings.storage_dir/owner/orphan).exists()
    result=retention.apply(plan['digest'],offline=True,now=now)
    assert result['failed_groups']==0 and not (settings.storage_dir/owner/orphan).exists()
    assert (settings.storage_dir/owner/known/'input.mp4').exists()
    report={'cli_preview_and_offline_guard':'passed','local_orphan_removed':True,'valid_source_preserved':True,'clock':'advanced two days for fixture grace only'}
    if settings.media_backend=='s3':
        local=settings.storage_dir/owner/known/'input.mp4'
        missing=str(uuid.uuid4());sid=str(uuid.uuid4());grant=str(uuid.uuid4())
        keys=[store.source_key(owner,missing,'.mp4'),store.upload_key(owner,sid,grant)]
        keep=store.source_key(owner,known,'.mp4')
        for key in [*keys,keep]:store.put(local,key,1024)
        plan=retention.preview('s3',now=now)
        result=retention.apply(plan['digest'],offline=True,backend='s3',now=now)
        assert result['failed_groups']==0
        assert store.client().head_object(Bucket=settings.s3_bucket,Key=keep)['ContentLength']>0
        for key in keys:
            assert not store.client().list_objects_v2(Bucket=settings.s3_bucket,Prefix=key).get('Contents')
        report.update(s3_orphans_removed=True,s3_valid_source_preserved=True)
    print(json.dumps(report))


if __name__=='__main__':main()
