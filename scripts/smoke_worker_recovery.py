"""Crash/restart proof using a private temporary DB and generated footage only."""
import json,os,secrets,subprocess,sys,tempfile,time,uuid
from pathlib import Path
from contextlib import ExitStack
ROOT=Path(__file__).resolve().parents[1]


def main():
    evidence=ROOT/'.data'/('worker-recovery-'+uuid.uuid4().hex);evidence.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='nextphase-worker-smoke-') as temporary, ExitStack() as cleanup:
        env=os.environ.copy();env.update(APP_ENV='test',QUEUE_BACKEND='database',WORKER_REQUIRE_SANDBOX='false',WORKER_REQUIRE_LIMITS='false',AUTH_MAIL_BACKEND='disabled',AUTH_MAIL_SEND_ENABLED='false',AUTH_REQUIRE_VERIFIED_EMAIL='false',AUTH_MAIL_DIR=temporary+'/auth-mail',PYTHONPATH=str(ROOT/'apps/api'),
            DATABASE_URL='sqlite:///'+temporary+'/db.sqlite3',STORAGE_DIR=temporary+'/media',
            JWT_SECRET=secrets.token_urlsafe(48),MEDIA_BACKEND='local',DIRECT_UPLOADS_ENABLED='false')
        os.environ.update(env);sys.path.insert(0,str(ROOT/'apps/api'))
        subprocess.run([sys.executable,'-m','app.migrate'],cwd=ROOT,env=env,check=True,timeout=30)
        from app.db import SessionLocal,engine
        # Windows cannot unlink SQLite while the SQLAlchemy pool retains handles.
        # ExitStack runs before TemporaryDirectory, on success and failure alike.
        cleanup.callback(engine.dispose)
        from app.models import User,RenderJob,RenderAttempt,utcnow
        from app.consent import RIGHTS_VERSION
        from app.worker import mark_done
        from app.media import probe_video
        from sqlalchemy import select
        from datetime import timedelta
        uid,jid=str(uuid.uuid4()),str(uuid.uuid4())
        source=Path(temporary)/'media'/uid/jid/'input.mp4';source.parent.mkdir(parents=True)
        subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30',
            '-t','5','-c:v','libx264','-threads','2','-pix_fmt','yuv420p',str(source)],check=True,timeout=30)
        with SessionLocal.begin() as db:
            db.add(User(id=uid,email=uid+'@example.com',password_hash='synthetic'));db.flush()
            db.add(RenderJob(id=jid,user_id=uid,title='Synthetic worker recovery',style='vlog',desired_seconds=5,
                source_duration_seconds=5,source_path=str(source),status='queued',rights_version=RIGHTS_VERSION,
                rights_confirmed_at=utcnow(),storage_reserved_bytes=134217728+source.stat().st_size,max_render_bytes=67108864))
        marker=Path(temporary)/'claimed'
        code="from app.worker import claim_job; from pathlib import Path; import sys,time; assert claim_job(); Path(sys.argv[1]).touch(); time.sleep(60)"
        with (evidence/'worker.log').open('w') as log:
            child=subprocess.Popen([sys.executable,'-c',code,str(marker)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+15
                while not marker.exists():
                    if child.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Disposable claimant failed')
                    time.sleep(.02)
                child.kill();child.wait(timeout=5)
                with SessionLocal.begin() as db:
                    job=db.get(RenderJob,jid);old=job.claim_token
                    assert job.status=='processing' and job.attempt_count==1
                    # Do not wait the production lease: only this killed disposable
                    # fixture's deadline is advanced, with no remaining writer.
                    job.lease_expires_at=utcnow()-timedelta(seconds=1)
                assert not mark_done(jid,old,error_code='LATE')
                restart="from app.worker import recover_stale_jobs,claim_job,process; assert recover_stale_jobs()==(1,0); job=claim_job(); assert job; process(job)"
                subprocess.run([sys.executable,'-c',restart],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
                with SessionLocal() as db:
                    job=db.get(RenderJob,jid);assert job.status=='succeeded' and job.attempt_count==2 and job.claim_token!=old
                    output=Path(job.output_path);attempts=list(db.scalars(select(RenderAttempt).where(RenderAttempt.job_id==jid)))
                    assert sorted(attempt.status for attempt in attempts)==['lease_lost','succeeded']
                assert not mark_done(jid,old,error_code='LATE')
                info=probe_video(output);assert info['width']==1080 and info['height']==1920 and 0<info['duration']<=5
                subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(output),'-f','null','-'],check=True,timeout=30)
                report={'crashed_claimant':True,'restarted_worker':'succeeded','attempts':2,'stale_publication':'refused',
                    'width':info['width'],'height':info['height'],'duration':info['duration'],
                    'lease':'advanced only for killed disposable fixture','scope':'not a production load/soak benchmark'}
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=5)

    assert not Path(temporary).exists()
    report['temporary_cleanup']='passed'
    (evidence/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Worker crash/restart:',json.dumps(report));print('Worker evidence:',evidence)


if __name__=='__main__':main()
