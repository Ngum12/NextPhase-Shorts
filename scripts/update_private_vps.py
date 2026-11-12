"""Explicit private-trial update: verified offsite backup, matching images, restart.

Run after pulling merged code. No git writes, provider setup or automatic rollback.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time

import vps_maintenance as maintenance

TIMERS=('nextphase-backup.timer','nextphase-monitor.timer')


def update(m=maintenance,run=subprocess.run):
    state=m.state_dir();phase='preflight';paused=False;active=[];timer_errors=[]
    def systemd(*args,check=True,interactive=False,timeout=120):
        result=run((['sudo','-v'] if interactive else ['sudo','-n','systemctl',*args]),
            check=False,timeout=timeout,**({} if interactive else {'capture_output':True,'text':True}))
        if check and result.returncode:raise RuntimeError('Systemd update step failed')
        return result
    def step(name):
        nonlocal phase
        phase=name;print(name.replace('_',' ').capitalize()+'...',flush=True)
    with (state/'update.lock').open('a') as lock:
        os.chmod(state/'update.lock',0o600)
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            step('administrator_access');systemd(interactive=True)
            step('checking_merged_checkout')
            if (m.command(['git','branch','--show-current']).strip()!='main'
                    or m.command(['git','status','--porcelain','--untracked-files=no']).strip()
                    or m.command(['git','rev-parse','HEAD']).strip()!=m.command(['git','rev-parse','origin/main']).strip()):
                raise RuntimeError('Pull a clean merged main checkout before updating')
            for timer in TIMERS:
                if systemd('is-active',timer,check=False).returncode==0:active.append(timer)
            backup_state=systemd('show','nextphase-backup.service','-p','ActiveState','--value').stdout.strip()
            if backup_state in ('active','activating','reloading','deactivating'):
                raise RuntimeError('Wait for existing backup')
            systemd('stop','nextphase-backup.timer')
            step('fresh_offsite_backup')
            systemd('start','nextphase-backup.service',timeout=3600)
            backup=m.read('backup-latest.json');cloud=m.read('offsite-latest.json')
            if (not backup.get('ok') or not backup.get('authenticated_readback') or not backup.get('offsite_copy')
                    or not cloud.get('ok') or not cloud.get('download_verified') or backup.get('file')!=cloud.get('file')
                    or backup.get('sha256')!=cloud.get('sha256') or m.read('paused-writers.json').get('paused')
                    or not 0<=time.time()-backup.get('completed_at',0)<900):
                raise RuntimeError('Verified fresh offsite backup required')
            name=backup.get('file','');digest=backup.get('sha256','')
            if (not isinstance(name,str) or not re.fullmatch(r'scheduled-\d{8}T\d{6}Z-[0-9a-f]{8}\.npb',name)
                    or not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest)):
                raise RuntimeError('Invalid backup identity')
            source=m.ROOT/'.data/scheduled-backups'/name
            if source.is_symlink() or not source.is_file():raise RuntimeError('Local recovery bundle missing')
            with source.open('rb') as handle:
                if hashlib.file_digest(handle,'sha256').hexdigest()!=digest:raise RuntimeError('Local recovery bundle changed')
            writers=m.running_writers()
            services=['api','worker','queue-supervisor','operator-agent','backup-tool','migrate']
            if 'mail-worker' in writers:services.append('mail-worker')
            step('building_matching_images')
            m.dc('build',*services,timeout=1800)
            step('worker_host_check')
            host=json.loads(m.dc('run','--rm','--no-deps','-T','worker','python','-m','app.worker_hostcheck',timeout=180))
            if host.get('ready') is not True:raise RuntimeError('Required worker host checks failed')
            systemd(interactive=True)
            systemd('stop','nextphase-monitor.timer','nextphase-monitor.service')
            step('checking_idle_queue')
            m.dc('exec','-T','api','python','-c',
                'from sqlalchemy import select,func; from app.db import SessionLocal; from app.models import RenderJob; '
                'db=SessionLocal(); assert db.scalar(select(func.count()).select_from(RenderJob).where('
                'RenderJob.status.in_(["queued","processing"])))==0; db.close()')
            step('stopping_writers');paused=True
            m.dc('stop',*writers)
            step('database_migration');m.dc('run','--rm','--no-deps','-T','migrate',timeout=300)
            step('starting_updated_services')
            m.dc('up','-d','--no-deps','--wait','--wait-timeout','120',*writers,timeout=180)
            paused=False
            step('schema_check')
            m.dc('exec','-T','api','python','-c',
                'from app.db import engine; from app.migrate import require_current_schema; require_current_schema(engine)')
            step('caption_font_check')
            m.dc('exec','-T','worker','python','-c',
                'from app.excerpt_render import CAPTION_FONT; assert CAPTION_FONT.is_file()')
            result={'ok':True,'updated_services':writers,'backup':backup['file'],'offsite_verified':True}
        except (Exception,KeyboardInterrupt) as error:
            result={'ok':False,'failed_step':phase,'writers_may_be_stopped':paused,
                    'error_type':type(error).__name__,'credentials_printed':False}
        finally:
            for timer in active:
                try:systemd('start',timer)
                except (Exception,KeyboardInterrupt):timer_errors.append(timer)
        if timer_errors:result.update(ok=False,timers_not_restored=timer_errors)
        else:result['timers_restored']=True
        m.save('update-latest.json',result)
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Run the verified private-trial update')
    args=parser.parse_args()
    if not args.apply:parser.error('Use --apply only after pulling merged code and closing the phone app.')
    os.umask(0o077)
    def interrupt(signum,frame):raise InterruptedError('Update interrupted')
    signal.signal(signal.SIGTERM,interrupt)
    if hasattr(signal,'SIGHUP'):signal.signal(signal.SIGHUP,interrupt)
    try:
        if not sys.platform.startswith('linux') or os.geteuid()==0:raise RuntimeError('Use the unprivileged VPS administrator')
        result=update()
    except (Exception,KeyboardInterrupt) as error:
        result={'ok':False,'failed_step':'preflight','error_type':type(error).__name__,'credentials_printed':False}
    print(json.dumps(result))
    if not result['ok']:raise SystemExit(1)


if __name__=='__main__':main()
