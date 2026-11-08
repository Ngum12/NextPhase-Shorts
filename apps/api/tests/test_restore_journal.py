import json
from datetime import timedelta
import os
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from app.config import get_settings
from app.migrate import upgrade_schema
from app.models import User,AuthSession,RefreshFamily,RenderJob,AccountDeletion,utcnow
from app.auth import make_password_hash
from app.restore_journal import Journal,JournalError,record
from app.restore_replay import replay,release,bind,require_binding

pytestmark=pytest.mark.skipif(os.name!='posix',reason='Independent journal requires Linux/POSIX local fsync/flock; use Docker on Windows')


@pytest.fixture
def journal(tmp_path,monkeypatch):
    key=Fernet.generate_key().decode();root=tmp_path/'independent'
    journal=Journal(root,key);journal.initialize()
    monkeypatch.setattr(get_settings(),'restore_journal_dir',str(root))
    monkeypatch.setattr(get_settings(),'restore_journal_key',key)
    return journal


def event(kind='revoke',**fields):
    return {'kind':kind,'owner':str(uuid.uuid4()),'project':None,'backend':None,'namespace':None,**fields}


def test_encrypted_durable_chain_and_concurrent_append(journal):
    owner=str(uuid.uuid4());payload=event(owner=owner)
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(lambda _:journal.append(payload),range(24)))
    current=journal.checkpoint();assert current['count']==24
    assert Journal(journal.root,get_settings().restore_journal_key).checkpoint()==current
    raw=(journal.root/'events.jsonl').read_bytes()
    assert owner.encode() not in raw and b'revoke' not in raw
    assert (journal.root/'events.jsonl').stat().st_mode & 0o777==0o600
    with pytest.raises(JournalError):journal.initialize()


@pytest.mark.parametrize('damage',['edit','reorder','duplicate','partial','tail','wrong-key','replace-stream'])
def test_tamper_and_old_checkpoint_refused(journal,tmp_path,damage):
    journal.append(event());old=journal.checkpoint();journal.append(event());current=journal.checkpoint()
    path=journal.root/'events.jsonl';lines=path.read_bytes().splitlines(keepends=True)
    if damage=='edit':lines[-1]=lines[-1].replace(b'payload',b'payloaD')
    elif damage=='reorder':lines[-1],lines[-2]=lines[-2],lines[-1]
    elif damage=='duplicate':lines.append(lines[-1])
    elif damage=='partial':lines[-1]=lines[-1][:-4]
    elif damage=='tail':lines=lines[:-1]
    elif damage=='wrong-key':journal=Journal(journal.root,Fernet.generate_key().decode())
    elif damage=='replace-stream':
        other=Journal(tmp_path/'replacement',get_settings().restore_journal_key);other.initialize()
        lines=(other.root/'events.jsonl').read_bytes().splitlines(keepends=True)
    path.write_bytes(b''.join(lines))
    with pytest.raises(JournalError):replay(journal,None,current)
    if damage=='tail':
        # An old checkpoint cannot prove freshness. Only the independently retained
        # current checkpoint detects a whole, valid prefix rollback.
        assert journal.checkpoint()==old


def test_permissions_and_symlink_refused(journal,tmp_path):
    path=journal.root/'events.jsonl';path.chmod(0o644)
    with pytest.raises(JournalError):journal.checkpoint()
    path.chmod(0o600);original=tmp_path/'saved';path.rename(original);path.symlink_to(original)
    with pytest.raises(JournalError):journal.checkpoint()


def test_write_failure_prevents_ack_and_db_change(client,journal,monkeypatch):
    email=uuid.uuid4().hex+'@example.com';password='restore-journal-password'
    pair=client.post('/api/v1/auth/register',json={'email':email,'password':password}).json()
    headers={'Authorization':'Bearer '+pair['access_token']}
    monkeypatch.setattr(Journal,'append',lambda *_:(_ for _ in ()).throw(JournalError()))
    assert client.post('/api/v1/auth/logout-all',headers=headers).status_code==503
    assert client.post('/api/v1/auth/password',headers=headers,json={'current_password':password,'new_password':'replacement-password'}).status_code==503
    assert client.post('/api/v1/account/delete',headers=headers,json={'current_password':password,'receipt_key':str(uuid.uuid4())}).status_code==503
    assert client.get('/api/v1/me',headers=headers).status_code==200
    assert client.post('/api/v1/auth/login',json={'email':email,'password':password}).status_code==200


def test_security_routes_record_without_codes_passwords_or_email(client,journal):
    email=uuid.uuid4().hex+'@example.com';password='restore-journal-password'
    pair=client.post('/api/v1/auth/register',json={'email':email,'password':password}).json()
    headers={'Authorization':'Bearer '+pair['access_token']}
    assert client.post('/api/v1/auth/password',headers=headers,json={'current_password':password,'new_password':'replacement-password'}).status_code==204
    pair=client.post('/api/v1/auth/login',json={'email':email,'password':'replacement-password'}).json()
    headers={'Authorization':'Bearer '+pair['access_token']}
    assert client.post('/api/v1/account/delete',headers=headers,json={'current_password':'replacement-password','receipt_key':str(uuid.uuid4())}).status_code==202
    with journal.locked():_,events=journal._read()
    assert {'password','revoke','account_delete'}<={row['kind'] for row in events}
    text=json.dumps(events)
    for secret in (email,password,'replacement-password',pair['access_token'],pair['refresh_token']):assert secret not in text


def test_offline_restore_fences_all_credentials_and_reapplies_post_snapshot_deletions(journal,tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'restored.db'))
    try:
        upgrade_schema(engine);bind(journal,engine,offline=True);uid,keep,jid,post=[str(uuid.uuid4()) for _ in range(4)]
        with Session(engine) as db,db.begin():
            for identity in (uid,keep):db.add(User(id=identity,email=identity+'@example.com',password_hash=make_password_hash('former-password')))
            db.flush()
            db.add(AuthSession(id='a'*64,user_id=keep,created_at=utcnow(),expires_at=utcnow()))
            db.add(RefreshFamily(id=str(uuid.uuid4()),user_id=keep,expires_at=utcnow()))
            db.add(RenderJob(id=jid,user_id=uid,title='restored source',style='vlog',desired_seconds=5,source_duration_seconds=5,source_path='private',status='succeeded'))
        # These requests happen AFTER the represented snapshot and survive outside it.
        journal.append(event('account_delete',owner=uid,namespace=[]))
        journal.append(event('project_delete',owner=keep,project=post,backend='s3',namespace='b'*64))
        checkpoint=journal.checkpoint()
        assert replay(journal,engine,checkpoint)['target_modified'] is False
        with Session(engine) as db:assert db.get(User,uid).deleted_at is None
        with pytest.raises(JournalError):replay(journal,engine,checkpoint,apply=True)
        result=replay(journal,engine,checkpoint,apply=True,offline=True)
        assert result['account_tombstones']==1 and result['project_tombstones']==1
        with pytest.raises(JournalError):journal.ready()
        with pytest.raises(JournalError):journal.append(event())
        with Session(engine) as db:
            assert db.get(User,uid).deleted_at and db.get(AccountDeletion,uid).media_cleaned_at is None
            assert db.get(RenderJob,jid).status=='deleted'
            assert db.get(RenderJob,post).status=='deleted' and db.get(RenderJob,post).object_store_id=='b'*64
            assert db.get(User,keep).deleted_at is None and db.get(User,keep).password_hash=='!restore-recovery-required'
            assert db.get(AuthSession,'a'*64).revoked_at
            assert all(row.revoked_at for row in db.scalars(select(RefreshFamily)))
        replay(journal,engine,checkpoint,apply=True,offline=True)  # Crash/retry safety.
        with pytest.raises(JournalError):release(journal,checkpoint)
        with pytest.raises(JournalError):release(journal,checkpoint,offline=True)  # Old signed capability retirement.
        release(journal,checkpoint,offline=True,now=utcnow()+timedelta(seconds=121))
        assert journal.ready()==checkpoint
    finally:engine.dispose()


def test_failed_replay_keeps_gate_and_rolls_back_target(journal,tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'failed.db'))
    try:
        upgrade_schema(engine);bind(journal,engine,offline=True);uid,other,jid=[str(uuid.uuid4()) for _ in range(3)]
        with Session(engine) as db,db.begin():
            for identity in (uid,other):db.add(User(id=identity,email=identity+'@example.com',password_hash='unchanged'))
            db.flush();db.add(RenderJob(id=jid,user_id=other,title='protected',style='vlog',desired_seconds=5,source_duration_seconds=5,source_path='private',status='succeeded'))
        journal.append(event('project_delete',owner=uid,project=jid,backend='local'))
        checkpoint=journal.checkpoint()
        with pytest.raises(JournalError):replay(journal,engine,checkpoint,apply=True,offline=True)
        with Session(engine) as db:assert db.get(User,other).password_hash=='unchanged' and db.get(RenderJob,jid).status=='succeeded'
        with pytest.raises(JournalError):journal.ready()
        with pytest.raises(JournalError):release(journal,checkpoint,offline=True)
    finally:engine.dispose()


def test_restore_hold_blocks_running_api_without_affecting_liveness(client,journal):
    from app.restore_replay import hold
    checkpoint=journal.checkpoint()
    with journal.locked():hold(journal,{'checkpoint':checkpoint,'applied':False,'release_after':utcnow().isoformat()})
    assert client.get('/health').status_code==200
    for path in ('/ready','/api/v1/me','/api/v1/styles'):
        response=client.get(path);assert response.status_code==503
        assert response.headers['cache-control']=='no-store'
    assert client.post('/api/v1/auth/register',json={'email':'unreachable@example.com','password':'not-submitted-password'}).status_code==503


def test_fsync_failure_is_not_acknowledged(client,journal,monkeypatch):
    email=uuid.uuid4().hex+'@example.com'
    pair=client.post('/api/v1/auth/register',json={'email':email,'password':'restore-journal-password'}).json()
    def fail(_):raise OSError('synthetic fsync failure')
    monkeypatch.setattr(os,'fsync',fail)
    response=client.post('/api/v1/auth/logout-all',headers={'Authorization':'Bearer '+pair['access_token']})
    assert response.status_code==503
    assert client.get('/api/v1/me',headers={'Authorization':'Bearer '+pair['access_token']}).status_code==200


def test_staging_requires_journal_and_media_tree_cannot_hold_it(monkeypatch):
    from app.restore_journal import configured
    monkeypatch.setattr(get_settings(),'restore_journal_dir','')
    monkeypatch.setattr(get_settings(),'env','staging')
    with pytest.raises(JournalError):configured()
    monkeypatch.setattr(get_settings(),'restore_journal_dir',str(get_settings().storage_dir/'bad-journal'))
    with pytest.raises(JournalError):configured()


def test_old_unbound_snapshot_and_missing_or_replaced_journal_refused(journal,tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'old.db'))
    try:
        upgrade_schema(engine)
        with pytest.raises(JournalError):require_binding(engine,journal)
        with pytest.raises(JournalError):replay(journal,engine,journal.checkpoint(),apply=True,offline=True)
        assert not (journal.root/'restore-hold.json').exists()
        bind(journal,engine,offline=True)
        require_binding(engine,journal)
        with pytest.raises(JournalError):require_binding(engine,None)
        replacement=Journal(tmp_path/'replacement',get_settings().restore_journal_key);replacement.initialize()
        with pytest.raises(JournalError):require_binding(engine,replacement)
        with pytest.raises(JournalError):bind(replacement,engine,offline=True)
    finally:engine.dispose()


def test_binding_bootstraps_existing_tombstones_before_protected_snapshot(journal,tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'bootstrap.db'))
    try:
        upgrade_schema(engine);uid,jid=str(uuid.uuid4()),str(uuid.uuid4());now=utcnow()
        with Session(engine) as db,db.begin():
            db.add(User(id=uid,email='!deleted:'+uid,password_hash='!disabled',deleted_at=now));db.flush()
            db.add(AccountDeletion(user_id=uid,receipt_hash='c'*64,receipt_expires_at=now,requested_at=now,cleanup_after=now,namespaces='[]'))
            db.add(RenderJob(id=jid,user_id=uid,title='Deleted project',style='vlog',desired_seconds=5,source_duration_seconds=5,source_path='',status='deleted'))
        result=bind(journal,engine,offline=True)
        assert result['existing_account_tombstones']==result['existing_project_tombstones']==1
        assert journal.checkpoint()['count']==2
        require_binding(engine,journal)
        assert bind(journal,engine,offline=True)['binding']=='already protected'
        assert journal.checkpoint()['count']==2
    finally:engine.dispose()
