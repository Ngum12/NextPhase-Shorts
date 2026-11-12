"""Update orchestration with fake sudo/Compose only; no actual VPS writes."""
import importlib.util
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import time

import pytest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('private_vps_update',ROOT/'scripts/update_private_vps.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def fixture(tmp_path,fail='',offsite=True,mail=False):
    events=[];saved={}
    name='scheduled-20261112T000000Z-12345678.npb'
    bundle=tmp_path/'.data/scheduled-backups'/name;bundle.parent.mkdir(parents=True);bundle.write_bytes(b'synthetic ciphertext')
    backup={'ok':True,'authenticated_readback':True,'offsite_copy':offsite,
            'file':name,'sha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),'completed_at':time.time()}
    class Maintenance:
        ROOT=tmp_path
        def command(self,args):
            if 'branch' in args:return 'main\n'
            if 'status' in args:return ''
            return 'synthetic-commit\n'
        def state_dir(self):return tmp_path
        def read(self,name):return {'backup-latest.json':backup,'offsite-latest.json':{**backup,'download_verified':offsite}}.get(name,{})
        def running_writers(self):return ['api','worker','queue-supervisor','operator-agent']+(['mail-worker'] if mail else [])
        def dc(self,*args,**kwargs):
            events.append(('dc',args))
            if fail and args[0]==fail:raise RuntimeError('fixture')
            return json.dumps({'ready':True}) if 'app.worker_hostcheck' in args else ''
        def save(self,name,value):saved[name]=value
    def run(args,**kwargs):
        events.append(('systemd',args))
        if fail=='backup' and 'nextphase-backup.service' in args and 'start' in args:
            return SimpleNamespace(returncode=1,stdout='')
        return SimpleNamespace(returncode=0,stdout='inactive\n' if 'show' in args else '')
    return Maintenance(),run,events,saved


def test_update_verifies_backup_before_build_and_preserves_observed_mail(tmp_path):
    m,run,events,saved=fixture(tmp_path,mail=True)
    result=module.update(m,run)
    assert result['ok'] and result['timers_restored'] and 'mail-worker' in result['updated_services']
    build=next(i for i,e in enumerate(events) if e[0]=='dc' and e[1][0]=='build')
    backup=next(i for i,e in enumerate(events) if 'nextphase-backup.service' in e[1] and 'start' in e[1])
    assert backup<build
    assert saved['update-latest.json']['offsite_verified']


@pytest.mark.parametrize('failure',['backup','build','stop','up'])
def test_update_failure_restores_timers_and_does_not_attempt_rollback(tmp_path,failure):
    m,run,events,_=fixture(tmp_path,fail=failure)
    result=module.update(m,run)
    assert not result['ok'] and result['timers_restored']
    assert result['writers_may_be_stopped']==(failure in ('stop','up'))
    for timer in module.TIMERS:assert any(e[0]=='systemd' and 'start' in e[1] and timer in e[1] for e in events)
    assert not any(e[0]=='dc' and 'down' in e[1] for e in events)


def test_missing_offsite_verification_refuses_build(tmp_path):
    m,run,events,_=fixture(tmp_path,offsite=False)
    result=module.update(m,run)
    assert not result['ok'] and result['failed_step']=='fresh_offsite_backup'
    assert not any(event[0]=='dc' for event in events)
    # A status claim is insufficient when the actual recovery file changed.
    m,run,events,_=fixture(tmp_path/'changed-bundle')
    next((m.ROOT/'.data/scheduled-backups').iterdir()).write_bytes(b'changed ciphertext')
    result=module.update(m,run)
    assert not result['ok'] and result['failed_step']=='fresh_offsite_backup'
    assert not any(event[0]=='dc' for event in events)


def test_dirty_checkout_stops_before_any_service_change(tmp_path):
    m,run,events,_=fixture(tmp_path)
    m.command=lambda args:'main' if 'branch' in args else ' M tracked-file'
    result=module.update(m,run)
    assert not result['ok'] and result['failed_step']=='checking_merged_checkout'
    assert not any(event[0]=='dc' for event in events)
    assert not any('stop' in event[1] for event in events)


def test_failed_timer_restoration_is_reported_as_failure(tmp_path):
    m,run,events,_=fixture(tmp_path)
    def failed_restore(args,**kwargs):
        if 'start' in args and 'nextphase-monitor.timer' in args:
            return SimpleNamespace(returncode=1,stdout='')
        return run(args,**kwargs)
    result=module.update(m,failed_restore)
    assert not result['ok'] and result['timers_not_restored']==['nextphase-monitor.timer']
