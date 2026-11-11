"""Maintenance recovery gates and notification throttling; no mail is sent."""
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

if os.name != 'posix':
    pytest.skip('Linux VPS maintenance only', allow_module_level=True)

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'scripts'))
spec = importlib.util.spec_from_file_location('vps_maintenance', ROOT/'scripts/vps_maintenance.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.fixture
def host(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'ROOT', tmp_path)
    (tmp_path/'.data').mkdir(mode=0o700)
    monkeypatch.setattr(m.shutil, 'disk_usage', lambda p: SimpleNamespace(free=100*m.GIB))
    return tmp_path


def fake_engine(monkeypatch, *, fail=None):
    import hashlib
    calls=[]
    payload=b'fake authenticated ciphertext'
    digest=hashlib.sha256(payload).hexdigest()
    def dc(*args, **kwargs):
        calls.append(args)
        if args[0]=='ps':
            return 'api\nworker\nqueue-supervisor\noperator-agent\ndb\nqueue\n'
        if args[0]=='stop' and fail=='stop':
            raise RuntimeError('partial stop')
        if args[0]=='up' and fail=='restart':
            raise RuntimeError('restart failed')
        if 'import os,json;print(json.dumps({"uid":os.getuid()}))' in args:
            return '{"uid":1000}'
        if 'api' in args and 'python' in args:
            return '1' if fail=='busy' else '0'
        if args[0]=='exec' and ('worker' in args or 'psql' in args):
            return '0'
        if kwargs.get('output'):
            if fail=='dump':
                raise RuntimeError('dump failed')
            Path(kwargs['output']).write_bytes(b'PGDMP fixture')
        if m.BACKUP_CODE in args:
            if fail=='archive':
                raise RuntimeError('archive failed')
            return json.dumps({'authenticated':True, 'sha256':digest})
        return ''
    def command(args, **kwargs):
        calls.append(tuple(args))
        if 'cp' in args:
            Path(args[-1]).write_bytes(b'wrong copy' if fail=='copy' else payload)
        return ''
    monkeypatch.setattr(m, 'dc', dc)
    monkeypatch.setattr(m, 'command', command)
    return calls


@pytest.mark.parametrize('failure', ['stop','dump','archive','copy'])
def test_backup_failure_resumes_only_previously_running_writers(host, monkeypatch, failure):
    calls=fake_engine(monkeypatch,fail=failure)
    with pytest.raises(RuntimeError):
        m.backup()
    starts=[c for c in calls if c[0]=='up']
    assert len(starts)==1
    assert set(starts[0][10:])=={'api','worker','queue-supervisor','operator-agent'}
    assert 'mail-worker' not in starts[0]
    assert not (host/'.data/maintenance/backup-latest.json').exists()
    assert m.read('paused-writers.json')=={'paused':False}


def test_busy_queue_does_not_stop_services(host,monkeypatch):
    calls=fake_engine(monkeypatch,fail='busy')
    with pytest.raises(RuntimeError):m.backup()
    assert not any(c[0] in ('stop','up') for c in calls)


def test_success_requires_readback_and_copy_hash_then_resumes(host,monkeypatch):
    calls=fake_engine(monkeypatch)
    result=m.backup()
    assert result['authenticated_readback'] and result['offsite_copy'] is False
    assert (host/'.data/scheduled-backups'/result['file']).stat().st_mode & 0o077 == 0
    assert m.read('backup-latest.json')['sha256']==result['sha256']
    assert any(c[0]=='setfacl' and 'u:1000:rx' in c for c in calls)
    assert any(c[0]=='up' for c in calls)
    assert not list((host/'.data/staging-input').iterdir())


def test_restart_failure_keeps_resume_marker(host,monkeypatch):
    fake_engine(monkeypatch,fail='restart')
    with pytest.raises(RuntimeError):m.backup()
    assert m.read('paused-writers.json')['paused']
    assert not m.read('backup-latest.json')
    fake_engine(monkeypatch)
    assert m.resume()['ok']
    assert m.read('paused-writers.json')=={'paused':False}


def test_no_pause_when_disk_reserve_is_missing(host,monkeypatch):
    calls=fake_engine(monkeypatch)
    monkeypatch.setattr(m.shutil,'disk_usage',lambda p:SimpleNamespace(free=m.GIB))
    with pytest.raises(RuntimeError):m.backup()
    assert not calls


def test_monitor_reports_disk_certificate_and_stale_backup(host,monkeypatch):
    monkeypatch.setattr(m.shutil,'disk_usage',lambda p:SimpleNamespace(free=m.GIB))
    monkeypatch.setattr(m,'certificate_days',lambda:5)
    monkeypatch.setattr(m,'dc',lambda *a,**k: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(m.urllib.request,'build_opener',lambda *a:SimpleNamespace(open=lambda *a,**k: (_ for _ in ()).throw(RuntimeError())))
    result=m.monitoring()
    assert set(result['issues'])=={'disk_below_5_gib','certificate_under_14_days',
        'backup_missing_or_older_than_30_hours','api_readiness_failed','worker_or_queue_monitor_failed'}


def test_email_acceptance_throttle_and_recovery_without_secret_output(host,monkeypatch):
    directory=m.state_dir()
    for name,content in [('email.json',json.dumps({'from':'monitor@example.com','to':'owner@example.com'})),('resend.key','fixture-only')]:
        path=directory/name;path.write_text(content);path.chmod(0o600)
    requests=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self):return b'{"id":"receipt-fixture"}'
    def send(request,**kwargs):
        requests.append(request)
        return Response()
    monkeypatch.setattr(m.urllib.request,'urlopen',send)
    failed={'ok':False,'issues':['api_readiness_failed']}
    assert m.notify(failed)=='provider_accepted_not_inbox_verified'
    assert m.notify(failed)=='unchanged_or_throttled'
    assert m.notify({'ok':True})=='provider_accepted_not_inbox_verified'
    assert len(requests)==2
    payload=json.loads(requests[0].data)
    assert requests[0].get_header('User-agent')=='NextPhase-VPS-Maintenance/1.0'
    assert requests[0].get_header('Accept')=='application/json'
    assert 'fixture-only' not in json.dumps(payload)
    assert payload['to']==['owner@example.com']
    assert m.notify({'ok':True},topic='backup')=='unchanged_or_throttled'


def test_units_use_rwanda_backup_time_and_recovery_hook(host,monkeypatch):
    monkeypatch.setattr(m.pwd,'getpwuid',lambda uid:SimpleNamespace(pw_name='nextphase'))
    result=m.units()
    path=Path(result['generated'])
    assert '02:00:00 UTC' in (path/'nextphase-backup.timer').read_text()
    assert 'ExecStopPost=' in (path/'nextphase-backup.service').read_text()
    assert ' resume' in (path/'nextphase-backup.service').read_text()
    assert 'User=nextphase' in (path/'nextphase-backup.service').read_text()
    assert '*:0/5:00 UTC' in (path/'nextphase-monitor.timer').read_text()
    with pytest.raises(RuntimeError):m.units()


def test_email_setup_uses_private_files_and_preserves_existing_key(host,monkeypatch,capsys):
    monkeypatch.setattr(m.sys.stdin,'isatty',lambda:True)
    monkeypatch.setattr(m.getpass,'getpass',lambda prompt:'fixture-only-not-a-real-key')
    assert m.email_setup('monitor@example.com','owner@example.com')['email_sent'] is False
    key=m.state_dir()/'resend.key'
    assert key.stat().st_mode & 0o077==0
    assert 'fixture-only-not-a-real-key' not in capsys.readouterr().out
    with pytest.raises(RuntimeError):m.email_setup('monitor@example.com','owner@example.com')
    assert key.read_text()=='fixture-only-not-a-real-key'


def test_email_diagnostics_do_not_echo_provider_bodies():
    import io
    import urllib.error
    error=urllib.error.HTTPError('https://api.resend.com/emails',403,'Forbidden',{},
        io.BytesIO(b'Cloudflare error code: 1010 sensitive-response-fixture'))
    details=m.email_error(error)
    assert details=={'issue':'email_delivery_failed','http_status':403,
                     'response_format':'non_json','edge_filter_marker':True}
    assert 'sensitive-response-fixture' not in json.dumps(details)
    error=urllib.error.HTTPError('https://api.resend.com/emails',401,'Unauthorized',{},
        io.BytesIO(b'{"name":"invalid_api_key","message":"sensitive-response-fixture"}'))
    details=m.email_error(error)
    assert details['provider_error']=='invalid_api_key'
    assert 'sensitive-response-fixture' not in json.dumps(details)


def offsite_fixture(host,monkeypatch):
    import hashlib
    cfg=host/'rclone.conf';cfg.write_text('fixture');cfg.chmod(0o600)
    folder=m.private_dir(host/'.data/scheduled-backups')
    name='scheduled-20261111T053525Z-a3f053b5.npb'
    path=folder/name;path.write_bytes(b'encrypted fixture')
    m.save('backup-latest.json',{'ok':True,'file':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                               'authenticated_readback':True,'offsite_copy':False,'completed_at':m.time.time()})
    settings={'remote':'nextphase-backups:NextPhase-Automated-Backups','config_file':str(cfg)}
    return settings,path


def test_offsite_upload_requires_full_readback_and_marks_matching_backup(host,monkeypatch):
    settings,path=offsite_fixture(host,monkeypatch)
    calls=[]
    monkeypatch.setattr(m,'command',lambda args,**kw:calls.append(args) or '')
    result=m.offsite_upload(settings)
    assert result['download_verified'] and result['offsite_copy']
    assert m.read('backup-latest.json')['offsite_copy']
    assert calls[0][3]=='copyto' and '--immutable' in calls[0] and '--checksum' in calls[0]
    assert calls[1][3]=='check' and '--download' in calls[1] and '--one-way' in calls[1]
    assert all('sync' not in c and 'delete' not in c for c in calls)
    assert '.kdbx' not in str(calls) and '.key' not in str(calls)


def test_offsite_readback_failure_does_not_claim_offsite_protection(host,monkeypatch):
    settings,path=offsite_fixture(host,monkeypatch)
    def failed(args,**kw):
        if 'check' in args:raise RuntimeError('remote differs')
        return ''
    monkeypatch.setattr(m,'command',failed)
    with pytest.raises(RuntimeError):m.offsite_upload(settings)
    assert m.read('backup-latest.json')['offsite_copy'] is False
    assert not m.read('offsite-latest.json')


def test_offsite_refuses_changed_local_ciphertext_before_upload(host,monkeypatch):
    settings,path=offsite_fixture(host,monkeypatch)
    path.write_bytes(b'changed')
    calls=[];monkeypatch.setattr(m,'command',lambda *a,**k:calls.append(a))
    with pytest.raises(RuntimeError):m.offsite_upload(settings)
    assert not calls


def test_offsite_does_not_mark_a_concurrent_new_backup_as_uploaded(host,monkeypatch):
    settings,path=offsite_fixture(host,monkeypatch)
    def upload(args,**kw):
        if 'check' in args:
            newer=m.read('backup-latest.json');newer['file']='newer.npb'
            m.save('backup-latest.json',newer)
        return ''
    monkeypatch.setattr(m,'command',upload)
    m.offsite_upload(settings)
    assert m.read('backup-latest.json')['offsite_copy'] is False


def test_offsite_setup_is_not_enabled_if_verification_fails(host,monkeypatch):
    monkeypatch.setattr(m,'command',lambda *a,**k:'nextphase-backups:\n')
    monkeypatch.setattr(m,'offsite_upload',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('failed')))
    with pytest.raises(RuntimeError):m.offsite_setup()
    assert not m.read('offsite.json')


def test_scheduled_upload_failure_preserves_local_backup_and_notifies(host,monkeypatch,capsys):
    settings,path=offsite_fixture(host,monkeypatch)
    m.save('offsite.json',{**settings,'enabled':True})
    monkeypatch.setattr(m.sys,'argv',['vps_maintenance.py','backup'])
    monkeypatch.setattr(m.signal,'signal',lambda *a:None)
    events=[]
    def local():
        events.append('local_backup_and_writer_restart')
        return m.read('backup-latest.json')
    def failed_upload():
        events.append('offsite_upload')
        raise RuntimeError('private-provider-response')
    def notify(result,**kwargs):
        events.append('failure_email')
        assert result['issues']==['offsite_copy_failed']
        return 'provider_accepted_not_inbox_verified'
    monkeypatch.setattr(m,'backup',local)
    monkeypatch.setattr(m,'offsite_upload',failed_upload)
    monkeypatch.setattr(m,'notify',notify)
    assert m.main()==1
    assert events==['local_backup_and_writer_restart','offsite_upload','failure_email']
    assert m.read('backup-latest.json')['ok']
    assert m.read('offsite-failure.json')['issue']=='offsite_copy_failed'
    assert 'private-provider-response' not in capsys.readouterr().out


def test_monitor_flags_stale_and_failed_offsite_copies(host,monkeypatch):
    import io
    offsite_fixture(host,monkeypatch)
    m.save('offsite.json',{'enabled':True})
    m.save('offsite-latest.json',{'verified_at':m.time.time()-31*3600})
    m.save('offsite-failure.json',{'checked_at':m.time.time()})
    monkeypatch.setattr(m,'certificate_days',lambda:90)
    monkeypatch.setattr(m,'dc',lambda *a,**k:'')
    monkeypatch.setattr(m.urllib.request,'build_opener',lambda *a:SimpleNamespace(
        open=lambda *a,**k:io.BytesIO(b'{"ok":true,"service":"nextphase-shorts"}')))
    result=m.monitoring()
    assert set(result['issues'])=={'offsite_copy_missing_or_older_than_30_hours','last_offsite_copy_failed'}
