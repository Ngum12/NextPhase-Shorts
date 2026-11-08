"""Disposable PostgreSQL: 100 simultaneous HTTP submissions, real soak and restore.
Never accepts an existing API/DB/media target. All service resources are owned here.
"""
import argparse,asyncio,hashlib,json,os,secrets,shutil,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=20)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--soak-seconds',type=int,default=600)
    args=parser.parse_args()
    if not 30<=args.soak_seconds<=3600:parser.error('Soak must be 30–3600 seconds')
    evidence=ROOT/'.data'/('capacity-exercise-'+uuid.uuid4().hex[:12]);evidence.mkdir(mode=0o700,parents=True)
    docker_env=os.environ.copy()
    for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):docker_env.pop(key,None)
    docker=['docker','--context','default'] if os.name=='nt' else ['docker','--host=unix:///var/run/docker.sock']
    def run(*cmd,**kw):return subprocess.run(docker+list(cmd),env=docker_env,check=True,timeout=90,**kw)
    name='np-capacity-'+uuid.uuid4().hex[:12];processes=[];logs=[]
    report={'schema_version':1,'scope':'disposable development PostgreSQL/CPU baseline; not production capacity/long-term soak certification'}
    try:
        run('run','-d','--name',name,'-p','127.0.0.1::5432','-e','POSTGRES_PASSWORD=synthetic-local-test',
            '-e','POSTGRES_DB=source_test','postgres:16-alpine',stdout=subprocess.DEVNULL)
        port=run('port',name,'5432/tcp',capture_output=True,text=True).stdout.strip().rsplit(':',1)[1]
        for _ in range(100):
            ready=subprocess.run(docker+['exec',name,'pg_isready','-U','postgres'],env=docker_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if ready.returncode==0:break
            time.sleep(.2)
        else:raise RuntimeError('Disposable PostgreSQL failed readiness')
        with tempfile.TemporaryDirectory(prefix='nextphase-capacity-') as temporary:
            media=Path(temporary)/'media'
            env={**os.environ,**{k+'_FILE':'' for k in ('JWT_SECRET','DATABASE_URL','S3_ACCESS_KEY_ID','S3_SECRET_ACCESS_KEY','QUEUE_PASSWORD','RESEND_API_KEY','AUTH_MAIL_ENCRYPTION_KEYS','RESTORE_JOURNAL_KEY')}}
            env.update(RESTORE_JOURNAL_DIR='',RESTORE_JOURNAL_KEY='',APP_ENV='test',QUEUE_BACKEND='database',MEDIA_BACKEND='local',DIRECT_UPLOADS_ENABLED='false',
                WORKER_REQUIRE_LIMITS='false',WORKER_REQUIRE_SANDBOX='false',AUTH_MAIL_BACKEND='disabled',AUTH_MAIL_SEND_ENABLED='false',AUTH_REQUIRE_VERIFIED_EMAIL='false',
                RESEND_API_KEY='',AUTH_MAIL_ENCRYPTION_KEYS='',AUTH_MAIL_DIR=temporary+'/mail',
                DATABASE_URL=f'postgresql+psycopg://postgres:synthetic-local-test@127.0.0.1:{port}/source_test',STORAGE_DIR=str(media),
                PYTHONPATH=str(ROOT/'apps/api'),JWT_SECRET=secrets.token_urlsafe(48),AI_PROVIDER='disabled',BILLING_PROVIDER='disabled',
                GLOBAL_ACTIVE_LIMIT='64',GLOBAL_PROCESSING_LIMIT='2',GLOBAL_STORAGE_BYTES=str(20*2**30),
                AUTH_REGISTER_IP_LIMIT='1000',AUTH_LOGIN_IP_LIMIT='1000',WORKER_POLL_SECONDS='.1',WORKER_HEARTBEAT_SECONDS='1')
            subprocess.run([sys.executable,'-m','app.migrate'],env=env,cwd=ROOT,check=True,timeout=60)
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));api_port=sock.getsockname()[1]
            base=f'http://127.0.0.1:{api_port}'
            def start_api():
                log=(evidence/('api-'+str(len(logs))+'.log')).open('w');logs.append(log)
                p=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(api_port),'--no-proxy-headers'],env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT);processes.append(p)
                with httpx.Client(trust_env=False,timeout=1) as c:
                    for _ in range(100):
                        if p.poll() is not None:raise RuntimeError('Disposable API exited')
                        try:
                            if c.get(base+'/ready').status_code==200:return p
                        except httpx.HTTPError:pass
                        time.sleep(.1)
                raise RuntimeError('Disposable API readiness failed')
            api=start_api();headers=[]
            with httpx.Client(base_url=base,trust_env=False,timeout=120) as client:
                for _ in range(100):
                    registered=client.post('/api/v1/auth/register',json={'email':uuid.uuid4().hex+'@example.com','password':secrets.token_urlsafe(24)})
                    assert registered.status_code==201
                    headers.append({'Authorization':'Bearer '+registered.json()['access_token']})
                payload={'file_name':'sample.mp4','total_bytes':1024,'title':'Synthetic capacity','style':'vlog','desired_seconds':15,
                    'rights_confirmed':True,'consent_version':'upload-rights-v1'}
                keys=[str(uuid.uuid4()) for _ in range(100)]
                async def burst():
                    event=asyncio.Event()
                    async with httpx.AsyncClient(base_url=base,trust_env=False,timeout=120,limits=httpx.Limits(max_connections=100,max_keepalive_connections=100)) as c:
                        async def submit(i):
                            await event.wait()
                            return await c.post('/api/v1/upload-sessions',json=payload,headers={**headers[i],'Idempotency-Key':keys[i]})
                        tasks=[asyncio.create_task(submit(i)) for i in range(100)];event.set()
                        return await asyncio.gather(*tasks)
                began=time.monotonic();responses=asyncio.run(burst())
                accepted=[i for i,r in enumerate(responses) if r.status_code==201]
                from collections import Counter
                print('Burst status counts:',dict(Counter(r.status_code for r in responses)),flush=True)
                print('Refusal reasons:',dict(Counter(r.json().get('detail','unknown') for r in responses if r.status_code==503)),flush=True)
                for r in responses:
                    if r.status_code not in (201,503):print('Unexpected synthetic response:',r.status_code,r.text[:200],flush=True);break
                assert len(accepted)==64 and sum(r.status_code==503 for r in responses)==36
                assert len({responses[i].json()['id'] for i in accepted})==64
                for i in accepted:
                    session=responses[i].json()['id']
                    replay=client.post('/api/v1/upload-sessions',json=payload,headers={**headers[i],'Idempotency-Key':keys[i]})
                    assert replay.status_code==200 and replay.json()['id']==session
                    assert client.get('/api/v1/upload-sessions/'+session,headers=headers[(i+1)%100]).status_code==404
                    assert client.post('/api/v1/upload-sessions/'+session+'/abort',headers=headers[i]).status_code==200
                subprocess.run([sys.executable,'-m','app.upload_cleanup'],env=env,cwd=ROOT,check=True,timeout=60)
                report['burst']={'concurrent_http_requests':100,'accepted':64,'capacity_refusals':36,'unique_sessions':64,'replays_and_owner_isolation':'passed','seconds':round(time.monotonic()-began,3)}
                print('100-request burst:',json.dumps(report['burst']),flush=True)
                for _ in range(2):
                    log=(evidence/('worker-'+str(len(logs))+'.log')).open('w');logs.append(log)
                    processes.append(subprocess.Popen([sys.executable,'-m','app.worker'],env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT))
                source=Path(temporary)/'sample.mp4'
                subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=30','-f','lavfi','-i','sine=frequency=440',
                    '-t','2','-c:v','libx264','-threads','2','-c:a','aac',str(source)],check=True,timeout=30)
                form={'title':'Original synthetic soak','style':'vlog','desired_seconds':'15','rights_confirmed':'true','consent_version':'upload-rights-v1'}
                def render(i):
                    response=client.post('/api/v1/jobs',headers={**headers[i],'Idempotency-Key':str(uuid.uuid4())},files={'file':('sample.mp4',source.read_bytes(),'video/mp4')},data=form)
                    assert response.status_code==201
                    job=response.json()['id'];deadline=time.monotonic()+90
                    while time.monotonic()<deadline:
                        state=client.get('/api/v1/jobs/'+job,headers=headers[i]).json()['status']
                        if state=='succeeded':break
                        assert state in ('queued','processing');time.sleep(.1)
                    else:raise RuntimeError('Soak job failed to complete')
                    result=client.get('/api/v1/jobs/'+job+'/download',headers=headers[i]);assert result.status_code==200 and len(result.content)>1000
                    assert client.get('/api/v1/jobs/'+job+'/download',headers=headers[(i+1)%100]).status_code==404
                    return job,hashlib.sha256(result.content).hexdigest()
                began=time.monotonic();cycles=0;canary=None;canary_hash=None;deleted=None
                while time.monotonic()-began<args.soak_seconds:
                    job,digest=render(cycles%3)
                    if cycles==0:canary,canary_hash=job,digest
                    else:
                        assert client.delete('/api/v1/jobs/'+job,headers=headers[cycles%3]).status_code==202
                        assert client.get('/api/v1/jobs/'+job+'/download',headers=headers[cycles%3]).status_code==404
                        if cycles==1:deleted=job
                    cycles+=1
                    until=min(began+args.soak_seconds,time.monotonic()+5)
                    while time.monotonic()<until:time.sleep(min(.5,until-time.monotonic()))
                report['soak']={'elapsed_seconds':round(time.monotonic()-began,3),'real_render_download_cycles':cycles,'owner_isolation_and_deletion':'passed','pattern':'2-second synthetic landscape/audio, three rotating owners, two worker processes; steady baseline, not mixed production workload'}
                print('Soak:',json.dumps(report['soak']),flush=True)
                for p in reversed(processes):stop(p)
                subprocess.run([sys.executable,'-m','app.deletion'],env=env,cwd=ROOT,check=True,timeout=60)
                # Consistent stopped-writer DB+media backup; generated credentials stay private.
                backup=evidence/'backup';backup.mkdir(mode=0o700)
                with (backup/'database.dump').open('wb') as handle:
                    run('exec',name,'pg_dump','-U','postgres','-d','source_test','-Fc',stdout=handle)
                (backup/'database.dump').chmod(0o600);shutil.copytree(media,backup/'media')
                manifest={str(p.relative_to(backup)):hashlib.sha256(p.read_bytes()).hexdigest() for p in backup.rglob('*') if p.is_file()}
                (backup/'manifest.json').write_text(json.dumps(manifest,indent=2));(backup/'manifest.json').chmod(0o600)
                run('exec',name,'psql','-U','postgres','-d','postgres','-c','CREATE DATABASE restored_test',stdout=subprocess.DEVNULL)
                with (backup/'database.dump').open('rb') as handle:
                    run('exec','-i',name,'pg_restore','-U','postgres','-d','restored_test','--exit-on-error','--no-owner',stdin=handle)
                for path,digest in manifest.items():assert hashlib.sha256((backup/path).read_bytes()).hexdigest()==digest
                shutil.rmtree(media);shutil.copytree(backup/'media',media)
                env['DATABASE_URL']=env['DATABASE_URL'].replace('/source_test','/restored_test')
                api=start_api()
                log=(evidence/'restored-worker.log').open('w');logs.append(log)
                processes.append(subprocess.Popen([sys.executable,'-m','app.worker'],env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT))
                restored=client.get('/api/v1/jobs/'+canary+'/download',headers=headers[0]);assert restored.status_code==200
                assert hashlib.sha256(restored.content).hexdigest()==canary_hash
                assert client.get('/api/v1/jobs/'+deleted+'/download',headers=headers[1]).status_code==404
                render(4) # Restored queue/mutex/schema must support new work too.
                report['restore']={'fresh_postgresql_database':True,'media_replaced_from_backup':True,'manifest_hashes':'passed',
                    'existing_auth_and_output_hash':'passed','deleted_project_stays_inaccessible':'passed','new_render_after_restore':'passed',
                    'scope':'consistent stopped-writer local PostgreSQL/media snapshot; encryption, offsite disaster recovery and post-snapshot deletion journal remain operator gates'}
                (evidence/'report.json').write_text(json.dumps(report,indent=2)+'\n')
                print('Restore:',json.dumps(report['restore']),flush=True)
    finally:
        for p in reversed(processes):stop(p)
        for log in logs:log.close()
        subprocess.run(docker+['rm','-fv',name],env=docker_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
    print('Capacity/restore evidence:',evidence)

if __name__=='__main__':main()
