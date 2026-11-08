"""Disposable HTTP backup-before-delete/restore proof; no existing target accepted.

Optional --postgres owns a temporary local PostgreSQL container (no image pull).
Journal and current checkpoint stay outside the restored DB/media snapshot.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid

import httpx
from cryptography.fernet import Fernet
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--postgres',action='store_true');parser.add_argument('--encrypted-backup',action='store_true');parser.add_argument('--test-postgres-container');args=parser.parse_args()
    if args.test_postgres_container:args.postgres=True
    evidence=ROOT/'.data'/('restore-journal-'+uuid.uuid4().hex);evidence.mkdir(mode=0o700,parents=True)
    with tempfile.TemporaryDirectory(prefix='nextphase-restore-') as temporary,ExitStack() as cleanup:
        directory=Path(temporary)
        env={**os.environ,**dict.fromkeys(['JWT_SECRET_FILE','DATABASE_URL_FILE','S3_ACCESS_KEY_ID_FILE','S3_SECRET_ACCESS_KEY_FILE','QUEUE_PASSWORD_FILE','RESEND_API_KEY_FILE','AUTH_MAIL_ENCRYPTION_KEYS_FILE','RESTORE_JOURNAL_KEY_FILE'],'')}
        env.update(BUDGET_STATE_FILE='',MIN_FREE_DISK_BYTES='0',APP_ENV='test',PYTHONPATH=str(ROOT/'apps/api'),QUEUE_BACKEND='database',WORKER_REQUIRE_SANDBOX='false',WORKER_REQUIRE_LIMITS='false',
            AUTH_MAIL_BACKEND='file',AUTH_MAIL_SEND_ENABLED='false',AUTH_REQUIRE_VERIFIED_EMAIL='false',AUTH_MAIL_DIR=temporary+'/mail',
            AUTH_LOGIN_IP_LIMIT='10000',AUTH_REGISTER_IP_LIMIT='10000',AUTH_PASSWORD_LIMIT='10000',
            JWT_SECRET=secrets.token_urlsafe(48),MEDIA_BACKEND='local',DIRECT_UPLOADS_ENABLED='false',STORAGE_DIR=temporary+'/media',
            DATABASE_URL='sqlite:///'+temporary+'/source.db',RESTORE_JOURNAL_DIR=temporary+'/independent',RESTORE_JOURNAL_KEY=Fernet.generate_key().decode())
        def run(*command,**kwargs):return subprocess.run(command,cwd=ROOT,env=env,check=True,timeout=90,**kwargs)
        docker=[];name=None
        source_db,restored_db,pg_user='source_test','restored_test','postgres'
        if args.postgres:
            docker=['docker','--host=unix:///var/run/docker.sock'];name='nextphase-restore-'+uuid.uuid4().hex
            if args.test_postgres_container:
                # Only an explicitly selected LOCAL disposable test service. Create
                # and drop fresh UUID databases; never restore into its existing DB.
                from sqlalchemy.engine import make_url
                test_url=make_url(os.environ.get('NEXTPHASE_TEST_DATABASE_URL',''))
                if test_url.host!='127.0.0.1' or not (test_url.database or '').endswith('_test') or not test_url.username:raise RuntimeError('Local _test database authority required')
                name=args.test_postgres_container;pg_user=test_url.username
                suffix=uuid.uuid4().hex;source_db='np_'+suffix+'_source_test';restored_db='np_'+suffix+'_restored_test'
                env['DATABASE_URL']=test_url.set(database=source_db).render_as_string(hide_password=False)
                def remove_databases():
                    for database in (source_db,restored_db):
                        subprocess.run([*docker,'exec',name,'psql','-U',pg_user,'-d','postgres','-c','DROP DATABASE IF EXISTS "'+database+'" WITH (FORCE)'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
                cleanup.callback(remove_databases)
            else:
                env['POSTGRES_PASSWORD']=secrets.token_urlsafe(32)
                run(*docker,'run','--pull=never','-d','--name',name,'--tmpfs','/var/lib/postgresql/data:rw,size=268435456',
                    '-e','POSTGRES_PASSWORD','-p','127.0.0.1::5432','postgres:16-alpine',stdout=subprocess.DEVNULL)
                cleanup.callback(lambda:subprocess.run([*docker,'rm','-f',name],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20))
                for _ in range(100):
                    ready=subprocess.run([*docker,'exec',name,'pg_isready','-h','127.0.0.1','-U',pg_user],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
                    if ready.returncode==0:break
                    time.sleep(.1)
                else:raise RuntimeError('Disposable PostgreSQL not ready')
                port=run(*docker,'port',name,'5432/tcp',capture_output=True,text=True).stdout.strip().split(':')[-1]
                env['DATABASE_URL']=f"postgresql+psycopg://postgres:{env['POSTGRES_PASSWORD']}@127.0.0.1:{port}/source_test"
            run(*docker,'exec',name,'psql','-U',pg_user,'-d','postgres','-c','CREATE DATABASE "'+source_db+'"',stdout=subprocess.DEVNULL)
        run(sys.executable,'-m','app.migrate',stdout=subprocess.DEVNULL)
        run(sys.executable,'-m','app.restore_replay','--init',stdout=subprocess.DEVNULL)
        run(sys.executable,'-m','app.restore_replay','--bind','--offline',stdout=subprocess.DEVNULL)
        source=directory/'pattern.mp4'
        run('ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=30','-t','2',
            '-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(source))
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        process=None
        def stop():
            nonlocal process
            if process is None:return
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            process=None
        cleanup.callback(stop)
        with (evidence/'api.log').open('w') as log,httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=30) as client:
            def start():
                nonlocal process
                process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port),'--no-proxy-headers'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                for _ in range(100):
                    try:
                        if client.get('/ready').status_code==200:return
                    except httpx.HTTPError:pass
                    if process.poll() is not None:raise RuntimeError('Disposable API startup refused')
                    time.sleep(.1)
                raise RuntimeError('Disposable API readiness timeout')
            start();password=secrets.token_urlsafe(20)
            def register():
                email=uuid.uuid4().hex+'@example.com'
                response=client.post('/api/v1/auth/register',json={'email':email,'password':password});assert response.status_code==201
                pair=response.json();auth={'Authorization':'Bearer '+pair['access_token']}
                return email,pair,auth,client.get('/api/v1/me',headers=auth).json()['id']
            deleted,kept,revoked=register(),register(),register()
            def upload(account):
                response=client.post('/api/v1/jobs',headers=account[2],files={'file':('source.mp4',source.read_bytes(),'video/mp4')},
                    data={'title':'Synthetic restore','style':'vlog','desired_seconds':'5','rights_confirmed':'true','consent_version':'upload-rights-v1'})
                assert response.status_code==201,response.text
                run(sys.executable,'-c','from app.worker import claim_job,process; job=claim_job(); assert job; process(job)',stdout=log,stderr=subprocess.STDOUT)
                jid=response.json()['id'];download=client.get('/api/v1/jobs/'+jid+'/download',headers=account[2]);assert download.status_code==200
                return jid,hashlib.sha256(download.content).hexdigest()
            first,_=upload(deleted);removed,_=upload(kept);canary,digest=upload(kept)
            stop()
            # Snapshot is older than all security requests below. Source DB is retained;
            # restore always targets a NEW database, never the only active copy.
            backup=directory/'backup';backup.mkdir(mode=0o700)
            shutil.copytree(directory/'media',backup/'media')
            if args.postgres:
                with (backup/'database.dump').open('wb') as handle:run(*docker,'exec',name,'pg_dump','-U',pg_user,'-Fc',source_db,stdout=handle)
            else:
                with sqlite3.connect(directory/'source.db') as origin,sqlite3.connect(backup/'database.db') as target:origin.backup(target)
            if args.encrypted_backup:
                private_key=directory/'separate-backup.key'
                run(sys.executable,'-m','app.backup_bundle','keygen','--key-file',str(private_key),stdout=subprocess.DEVNULL)
                snapshot_checkpoint=directory/'snapshot-checkpoint.json'
                with snapshot_checkpoint.open('wb') as handle:run(sys.executable,'-m','app.restore_replay','--checkpoint',stdout=handle)
                dump=backup/('database.dump' if args.postgres else 'database.db')
                encrypted=directory/'encrypted.npb'
                run(sys.executable,'-m','app.backup_bundle','create','--key-file',str(private_key),'--database-dump',str(dump),'--media',str(backup/'media'),'--checkpoint',str(snapshot_checkpoint),'--output',str(encrypted),'--offline',stdout=subprocess.DEVNULL)
            start()
            assert client.post('/api/v1/account/delete',headers=deleted[2],json={'current_password':password,'receipt_key':str(uuid.uuid4())}).status_code==202
            assert client.delete('/api/v1/jobs/'+removed,headers=kept[2]).status_code==202
            assert client.post('/api/v1/auth/password',headers=revoked[2],json={'current_password':password,'new_password':secrets.token_urlsafe(20)}).status_code==204
            assert client.post('/api/v1/auth/logout-all',headers=kept[2]).status_code==204
            stop()
            checkpoint=directory/'current-checkpoint.json'
            with checkpoint.open('wb') as handle:run(sys.executable,'-m','app.restore_replay','--checkpoint',stdout=handle)
            if args.encrypted_backup:
                recovered=directory/'authenticated-recovery'
                run(sys.executable,'-m','app.backup_bundle','restore','--key-file',str(private_key),'--bundle',str(encrypted),'--output',str(recovered),stdout=subprocess.DEVNULL)
                backup=recovered
            if args.postgres:
                run(*docker,'exec',name,'psql','-U',pg_user,'-d','postgres','-c','CREATE DATABASE "'+restored_db+'"',stdout=subprocess.DEVNULL)
                with (backup/'database.dump').open('rb') as handle:run(*docker,'exec','-i',name,'pg_restore','-U',pg_user,'-d',restored_db,'--exit-on-error','--no-owner',stdin=handle)
                env['DATABASE_URL']=env['DATABASE_URL'].replace('/'+source_db,'/'+restored_db)
            else:
                shutil.copyfile(backup/('database.dump' if args.encrypted_backup else 'database.db'),directory/'restored.db');env['DATABASE_URL']='sqlite:///'+temporary+'/restored.db'
            shutil.rmtree(directory/'media');shutil.copytree(backup/'media',directory/'media')
            command=[sys.executable,'-m','app.restore_replay','--replay','--expected-checkpoint',str(checkpoint)]
            preview=json.loads(run(*command,capture_output=True,text=True).stdout);assert preview['target_modified'] is False
            applied=json.loads(run(*command,'--apply','--offline',capture_output=True,text=True).stdout)
            assert applied['account_tombstones']==1 and applied['project_tombstones']==1
            # API cannot reopen until explicit release, including a restart after replay.
            refusal=run(sys.executable,'-c',"from app.restore_journal import configured,JournalError\ntry: configured().ready()\nexcept JournalError: pass\nelse: raise AssertionError('restore gate missing')",stdout=subprocess.DEVNULL)
            # Advance only the stopped disposable fixture's release clock, never an
            # operator journal/production time. CLI production release has no bypass.
            run(sys.executable,'-c',"from app.restore_replay import release,expected_checkpoint; from app.restore_journal import configured; from app.models import utcnow; from datetime import timedelta; import sys; release(configured(),expected_checkpoint(sys.argv[1]),offline=True,now=utcnow()+timedelta(seconds=121))",str(checkpoint),stdout=subprocess.DEVNULL)
            start()
            for account in (deleted,kept,revoked):
                assert client.get('/api/v1/me',headers=account[2]).status_code==401
                assert client.post('/api/v1/auth/login',json={'email':account[0],'password':password}).status_code==401
                assert client.post('/api/v1/auth/refresh',json={'refresh_token':account[1]['refresh_token'],'rotation_key':str(uuid.uuid4())}).status_code==401
            # A fresh proof in this disposable FILE backend restores only a survivor.
            assert client.post('/api/v1/auth/password-reset/request',json={'email':kept[0]}).status_code==202
            messages=[]
            for _ in range(100):
                messages=list((directory/'mail').glob('*.json'))
                if messages:break
                time.sleep(.05)
            assert len(messages)==1
            message=json.loads(messages[0].read_text());code=message.get('code')
            assert code,'Local fixture code unavailable'
            fresh_password=secrets.token_urlsafe(20)
            assert client.post('/api/v1/auth/password-reset/confirm',json={'code':code,'new_password':fresh_password}).status_code==204
            response=client.post('/api/v1/auth/login',json={'email':kept[0],'password':fresh_password});assert response.status_code==200
            fresh={'Authorization':'Bearer '+response.json()['access_token']}
            assert client.get('/api/v1/jobs/'+removed,headers=fresh).status_code==404
            download=client.get('/api/v1/jobs/'+canary+'/download',headers=fresh);assert download.status_code==200 and hashlib.sha256(download.content).hexdigest()==digest
            stop()
            # Advance cleanup wait only for stopped disposable fixtures, not live clocks.
            proof="""from app.db import SessionLocal,engine
from app.models import AccountDeletion,RenderJob,utcnow
from app.account_deletion import cleanup_accounts
from app.deletion import cleanup_deleted
from datetime import timedelta
from pathlib import Path
import sys
uid,removed,canary=sys.argv[1:]
with SessionLocal.begin() as db:
 db.get(AccountDeletion,uid).cleanup_after=utcnow()-timedelta(seconds=1)
 db.get(RenderJob,removed).cleanup_after=utcnow()-timedelta(seconds=1)
cleanup_accounts();cleanup_deleted()
with SessionLocal() as db:
 assert db.get(AccountDeletion,uid).media_cleaned_at
 assert db.get(RenderJob,removed).media_deleted_at
 assert Path(db.get(RenderJob,canary).output_path).exists()
engine.dispose()
"""
            run(sys.executable,'-c',proof,deleted[3],removed,canary,stdout=subprocess.DEVNULL)
            report={'backend':'postgres' if args.postgres else 'sqlite','snapshot_before_requests':True,'new_database_target':True,
                'journal_outside_snapshot':True,'encrypted_backup':args.encrypted_backup,'account_and_project_deletion':'reapplied','old_access_refresh_password':'rejected',
                'explicit_release_gate':'passed','fresh_recovery':'passed (local test file; no email sent)',
                'surviving_output_hash':'preserved','deleted_media_cleanup':'passed','scope':'disposable; not offsite/provider/production acceptance'}
            (evidence/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));print('Evidence:',evidence)


if __name__=='__main__':main()
