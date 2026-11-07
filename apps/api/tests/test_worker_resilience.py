"""Fair turns, bounded recovery, shutdown and Linux render containment."""
from datetime import timedelta
import json,os,signal,subprocess,sys,time
from pathlib import Path
import pytest
from sqlalchemy import select
from app.db import SessionLocal
from app.models import RenderJob,RenderAttempt,utcnow
from app.worker import claim_job,mark_done,process,recover_stale_jobs,settings
from test_api import new_user
from upload_fixtures import RIGHTS_FORM


def submit(client,token):
    response=client.post('/api/v1/jobs',headers={'Authorization':'Bearer '+token},
        files={'file':('source.mp4',b'synthetic','video/mp4')},data=RIGHTS_FORM)
    assert response.status_code==201,response.text
    return response.json()['id']


def test_accounts_rotate_before_oldest_backlog_and_keep_internal_fifo(client,monkeypatch):
    monkeypatch.setattr('app.main.probe_video',lambda _: {'duration':2})
    first=new_user(client);a=[submit(client,first) for _ in range(3)]
    second=new_user(client);b=[submit(client,second) for _ in range(2)]
    order=[]
    for _ in range(5):
        claimed=claim_job();order.append(claimed['id']);assert mark_done(claimed['id'],claimed['claim_token'],error_code='TEST')
    assert order==[a[0],b[0],a[1],b[1],a[2]]


def test_recovery_is_bounded_preserves_live_leases_and_fences_old_tokens(client,monkeypatch):
    from test_worker import queued_job
    ids=[queued_job(client,monkeypatch)[0] for _ in range(4)]
    claims=[claim_job() for _ in ids]
    with SessionLocal.begin() as db:
        for jid in ids[:3]:db.get(RenderJob,jid).lease_expires_at=utcnow()-timedelta(seconds=1)
    assert recover_stale_jobs(limit=2)==(2,0)
    with SessionLocal() as db:
        assert sum(db.get(RenderJob,jid).status=='queued' for jid in ids)==2
        assert db.get(RenderJob,ids[3]).status=='processing'
    assert recover_stale_jobs(limit=2)==(1,0)
    for old in claims[:3]:assert not mark_done(old['id'],old['claim_token'],error_code='LATE')
    for _ in range(3):
        retry=claim_job();assert retry['id'] in ids[:3]
        with SessionLocal.begin() as db:db.get(RenderJob,retry['id']).lease_expires_at=utcnow()-timedelta(seconds=1)
        # Process retries later so this claimant cannot take the same expired job.
    assert recover_stale_jobs()==(0,3)
    for old in claims:mark_done(old['id'],old['claim_token'],error_code='TEST')
    for limit in (0,1001):
        with pytest.raises(ValueError):recover_stale_jobs(limit)


def test_shutdown_expires_only_its_claim_after_child_teardown(client,monkeypatch):
    from test_worker import queued_job
    jid,_=queued_job(client,monkeypatch);job=claim_job()
    monkeypatch.setattr('app.worker.stop',True);process(job)
    assert not mark_done(jid,job['claim_token'],error_code='LATE')
    assert recover_stale_jobs()==(1,0)
    monkeypatch.setattr('app.worker.stop',False)
    retry=claim_job();assert retry['id']==jid and retry['claim_token']!=job['claim_token']
    assert mark_done(jid,retry['claim_token'],error_code='TEST')


def test_database_outage_is_retried_without_logging_private_exception(monkeypatch,caplog):
    import app.worker as worker
    from sqlalchemy.exc import OperationalError
    monkeypatch.setattr(worker,'require_current_schema',lambda _:None)
    monkeypatch.setattr(worker,'stop',False)
    monkeypatch.setattr(worker.signal,'signal',lambda *_:None)
    monkeypatch.setattr('app.upload_cleanup.cleanup_uploads',lambda:None)
    monkeypatch.setattr('app.auth_limits.cleanup_auth',lambda:None)
    monkeypatch.setattr('app.deletion.cleanup_deleted',lambda:None)
    monkeypatch.setattr('app.account_deletion.cleanup_accounts',lambda:None)
    def unavailable():raise OperationalError('private-password-and-path',{},Exception('secret'))
    monkeypatch.setattr(worker,'recover_stale_jobs',unavailable)
    monkeypatch.setattr(worker.time,'sleep',lambda _:setattr(worker,'stop',True))
    worker.main();assert 'database unavailable' in caplog.text and 'private-password' not in caplog.text


def wait_for_file(path,child):
    deadline=time.monotonic()+10
    while True:
        try:return json.loads(path.read_text())
        except (FileNotFoundError,json.JSONDecodeError):pass
        # Creation and writing are separate: an existing marker may still be
        # empty/partial on a busy runner. Wait for complete data, not existence.
        assert child.poll() is None,'Synthetic render parent exited early'
        assert time.monotonic()<deadline,'Synthetic render never started'
        time.sleep(.02)


def running(pid):
    try:
        # Linux orphan zombies have exited and consume no CPU; PID 1 controls reaping.
        return Path(f'/proc/{pid}/stat').read_text().split(') ',1)[1].split()[0]!='Z'
    # procfs may return ENOENT on open or ESRCH during read as a process exits.
    except (FileNotFoundError,ProcessLookupError):return False


@pytest.mark.parametrize('error',[FileNotFoundError,ProcessLookupError])
def test_exited_process_observation_accepts_both_procfs_exit_errors(monkeypatch,error):
    def gone(*args,**kwargs):raise error('Synthetic exited process')
    monkeypatch.setattr(Path,'read_text',gone)
    assert running(123) is False


@pytest.mark.parametrize('state,expected',[('R',True),('Z',False)])
def test_live_processes_remain_live_and_zombies_are_exited(monkeypatch,state,expected):
    monkeypatch.setattr(Path,'read_text',lambda *_args,**_kwargs:f'123 (synthetic) {state} 1 2 3')
    assert running(123) is expected


def test_process_observation_does_not_hide_other_errors(monkeypatch):
    def denied(*args,**kwargs):raise PermissionError('Synthetic permission failure')
    monkeypatch.setattr(Path,'read_text',denied)
    with pytest.raises(PermissionError):running(123)


def test_marker_waits_for_complete_json(monkeypatch):
    from types import SimpleNamespace
    values=iter(['','{"pid":123}'])
    monkeypatch.setattr(Path,'read_text',lambda *_args,**_kwargs:next(values))
    monkeypatch.setattr(time,'sleep',lambda _:None)
    assert wait_for_file(Path('synthetic-marker'),SimpleNamespace(poll=lambda:None))=={'pid':123}


@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux kernel parent-death/rlimit behavior')
def test_hard_worker_crash_kills_live_render_and_strips_credentials(tmp_path,monkeypatch):
    marker=tmp_path/'child.json';fake=tmp_path/'ffmpeg'
    fake.write_text(f'#!{sys.executable}\nimport json,os,resource,sys,time\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(json.dumps({{"pid":os.getpid(),"secret_present":"JWT_SECRET" in os.environ or "S3_SECRET_ACCESS_KEY" in os.environ,"cpu":resource.getrlimit(resource.RLIMIT_CPU)[0],"core":resource.getrlimit(resource.RLIMIT_CORE)[0],"files":resource.getrlimit(resource.RLIMIT_NOFILE)[0]}}))\ntime.sleep(60)\n')
    fake.chmod(0o700)
    env=os.environ.copy();env.update(PATH=str(tmp_path)+os.pathsep+env['PATH'],JWT_SECRET='synthetic-secret',S3_SECRET_ACCESS_KEY='synthetic-key')
    code="from app.media import run_render; import sys; run_render(['ffmpeg',sys.argv[1]],30,lambda:False)"
    parent=subprocess.Popen([sys.executable,'-c',code,str(marker)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    pid=None
    try:
        data=wait_for_file(marker,parent);pid=data['pid']
        assert running(pid) and not data['secret_present']
        assert data['cpu']==90 and data['core']==0 and data['files']==128
        parent.kill();parent.wait(timeout=5)
        deadline=time.monotonic()+5
        while running(pid) and time.monotonic()<deadline:time.sleep(.02)
        assert not running(pid),'FFmpeg survived a hard worker crash'
    finally:
        if parent.poll() is None:parent.kill();parent.wait(timeout=5)
        if pid and running(pid):os.killpg(pid,signal.SIGKILL)


@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux process group containment')
def test_timeout_kills_render_process_group(tmp_path,monkeypatch):
    from app.media import run_render
    marker=tmp_path/'group.json';fake=tmp_path/'ffmpeg'
    fake.write_text(f'#!{sys.executable}\nimport subprocess,sys,os,json,time\nfrom pathlib import Path\nchild=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"])\nPath(sys.argv[1]).write_text(json.dumps([os.getpid(),child.pid]))\ntime.sleep(60)\n')
    fake.chmod(0o700);monkeypatch.setenv('PATH',str(tmp_path)+os.pathsep+os.environ['PATH'])
    with pytest.raises(subprocess.TimeoutExpired):run_render(['ffmpeg',str(marker)],1,lambda:False)
    pids=json.loads(marker.read_text())
    deadline=time.monotonic()+5
    while any(running(pid) for pid in pids) and time.monotonic()<deadline:time.sleep(.02)
    assert not any(running(pid) for pid in pids)


def test_hundred_submission_burst_keeps_owner_limits_and_fair_turns(client,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr('app.main.probe_video',lambda _: {'duration':2})
    tokens=[new_user(client) for _ in range(10)]
    def upload(index):
        token=tokens[index%10]
        return index%10,client.post('/api/v1/jobs',headers={'Authorization':'Bearer '+token},
            files={'file':('source.mp4',b'synthetic','video/mp4')},data=RIGHTS_FORM)
    accepted=[]
    with ThreadPoolExecutor(max_workers=16) as pool:responses=list(pool.map(upload,range(100)))
    for owner in range(10):
        owned=[response for index,response in responses if index==owner]
        assert sum(response.status_code==201 for response in owned)==3
        assert sum(response.status_code==429 for response in owned)==7
        accepted.extend(response.json()['id'] for response in owned if response.status_code==201)
    assert len(set(accepted))==30
    try:
        for _ in range(3):
            round_owners=set()
            for _ in range(10):
                job=claim_job();assert job and job['id'] in accepted and job['user_id'] not in round_owners
                round_owners.add(job['user_id'])
                assert mark_done(job['id'],job['claim_token'],error_code='TEST')
            assert len(round_owners)==10
    finally:
        with SessionLocal.begin() as db:
            from sqlalchemy import update
            db.execute(update(RenderJob).where(RenderJob.id.in_(accepted),RenderJob.status.in_(['queued','processing']))
                .values(status='cancelled',claim_token=None,lease_expires_at=None))


@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux CPU rlimit enforcement')
def test_decoder_cpu_limit_terminates_a_runaway_child(tmp_path):
    fake=tmp_path/'ffmpeg';fake.write_text(f'#!{sys.executable}\nwhile True: pass\n');fake.chmod(0o700)
    env=os.environ.copy();env['PATH']=str(tmp_path)+os.pathsep+env['PATH']
    result=subprocess.run([sys.executable,'-m','app.render_child',str(os.getpid()),'1','ffmpeg'],
        env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
    assert result.returncode==-signal.SIGKILL


@pytest.mark.parametrize('memory,cpu,pids',[
 ('max','200000 100000','128'),('2147483649','200000 100000','128'),
 ('2147483648','max 100000','128'),('2147483648','300000 100000','128'),
 ('2147483648','200000 100000','max'),('2147483648','200000 100000','129'),
])
def test_unenforced_container_limits_fail_closed(tmp_path,monkeypatch,memory,cpu,pids):
    from app.worker_limits import require_worker_limits
    monkeypatch.setattr('app.worker_limits.sys.platform','linux')
    for name,value in [('memory.max',memory),('cpu.max',cpu),('pids.max',pids)]:
        (tmp_path/name).write_text(value)
    with pytest.raises(RuntimeError,match='requires enforced cgroup'):require_worker_limits(tmp_path)


def test_required_container_limits_accept_only_bounded_readable_configuration(tmp_path,monkeypatch):
    from app.worker_limits import require_worker_limits
    monkeypatch.setattr('app.worker_limits.sys.platform','linux')
    with pytest.raises(RuntimeError):require_worker_limits(tmp_path)
    for name,value in [('memory.max','2147483648'),('cpu.max','200000 100000'),('pids.max','128')]:
        (tmp_path/name).write_text(value)
    require_worker_limits(tmp_path)
