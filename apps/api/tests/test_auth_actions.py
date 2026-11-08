"""No email provider: private local proof codes, races, expiry and revocation."""
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import json,os,uuid
import pytest
from sqlalchemy import select
from app.config import get_settings,Settings
from app.db import SessionLocal
from app.models import AuthAction,User,utcnow
from app.auth_action_tokens import token_hash
from test_api import new_user

PASSWORD='correct horse battery staple'
NEW='a new secure password for testing'


def headers(token):return {'Authorization':'Bearer '+token}
def profile(client,token):return client.get('/api/v1/me',headers=headers(token)).json()
def reset_request(client,email):return client.post('/api/v1/auth/password-reset/request',json={'email':email})
def confirm(client,code,password=NEW):return client.post('/api/v1/auth/password-reset/confirm',json={'code':code,'new_password':password})


@pytest.fixture
def inbox(monkeypatch,tmp_path):
    settings=get_settings();monkeypatch.setattr(settings,'auth_mail_backend','file')
    monkeypatch.setattr(settings,'auth_mail_dir',tmp_path/'inbox')
    return settings.auth_mail_dir


def messages(inbox):return sorted([json.loads(path.read_text()) for path in inbox.glob('*.json')],key=lambda row:row['expires_at'])
def latest(inbox,purpose):return [row for row in messages(inbox) if row['purpose']==purpose][-1]['code']


def test_disabled_delivery_never_issues_code_or_allows_reset(client):
    token=new_user(client);email=profile(client,token)['email']
    assert client.get('/api/v1/auth/recovery-capabilities').json()=={'delivery':'disabled','verification_enforced':False}
    assert reset_request(client,email).status_code==202
    with SessionLocal() as db:
        assert not db.scalar(select(AuthAction).where(AuthAction.user_id==profile(client,token)['id']))
    assert confirm(client,'a'*43).status_code==503
    assert client.get('/api/v1/me',headers=headers(token)).status_code==200


def test_reset_generic_requests_hash_only_single_use_and_all_sessions_revoked(client,inbox):
    token=new_user(client);me=profile(client,token)
    other_pair=client.post('/api/v1/auth/login',json={'email':me['email'],'password':PASSWORD}).json()
    other_session=other_pair['access_token']
    known=reset_request(client,me['email']);unknown=reset_request(client,'absent-'+uuid.uuid4().hex+'@example.com')
    assert known.status_code==unknown.status_code==202 and known.json()==unknown.json()=={'status':'accepted'}
    assert known.headers['cache-control']=='no-store'
    assert len(messages(inbox))==1;code=latest(inbox,'reset')
    assert code not in known.text and len(code)==43
    with SessionLocal() as db:
        action=db.scalar(select(AuthAction).where(AuthAction.user_id==me['id']))
        assert action.token_hash==token_hash(code) and code not in action.token_hash
    assert confirm(client,code).status_code==204
    assert client.post('/api/v1/auth/refresh',json={'refresh_token':other_pair['refresh_token'],'rotation_key':str(uuid.uuid4())}).status_code==401
    for access in (token,other_session):assert client.get('/api/v1/me',headers=headers(access)).status_code==401
    assert confirm(client,code).status_code==400
    assert client.post('/api/v1/auth/login',json={'email':me['email'],'password':PASSWORD}).status_code==401
    assert client.post('/api/v1/auth/login',json={'email':me['email'],'password':NEW}).status_code==200
    if os.name=='posix':
        assert inbox.stat().st_mode&0o077==0
        assert all(path.stat().st_mode&0o077==0 for path in inbox.glob('*.json'))


def test_verification_requires_auth_and_cannot_be_repurposed_for_reset(client,inbox):
    token=new_user(client)
    assert client.post('/api/v1/auth/email-verification/request').status_code==401
    assert client.post('/api/v1/auth/email-verification/request',headers=headers(token)).status_code==202
    code=latest(inbox,'verify')
    assert confirm(client,code).status_code==400
    assert client.post('/api/v1/auth/email-verification/confirm',json={'code':code}).status_code==204
    me=profile(client,token)
    assert me['email_verified_at'] and me['email_verification_method']=='local_file'
    assert client.post('/api/v1/auth/email-verification/confirm',json={'code':code}).status_code==400
    assert client.post('/api/v1/auth/email-verification/request',headers=headers(token)).status_code==202
    assert len(messages(inbox))==1


def test_expired_wrong_purpose_and_credential_changed_codes_rejected(client,inbox):
    token=new_user(client);me=profile(client,token);reset_request(client,me['email']);code=latest(inbox,'reset')
    assert client.post('/api/v1/auth/email-verification/confirm',json={'code':code}).status_code==400
    with SessionLocal.begin() as db:
        action=db.scalar(select(AuthAction).where(AuthAction.token_hash==token_hash(code)))
        action.expires_at=utcnow()-timedelta(seconds=1)
    assert confirm(client,code).status_code==400
    reset_request(client,me['email']);code=latest(inbox,'reset')
    assert client.post('/api/v1/auth/password',headers=headers(token),json={'current_password':PASSWORD,'new_password':NEW}).status_code==204
    assert confirm(client,code).status_code==400
    with SessionLocal() as db:assert all(row.used_at for row in db.scalars(select(AuthAction).where(AuthAction.user_id==me['id'])))


def test_parallel_reset_proofs_publish_one_new_password(client,inbox):
    token=new_user(client);email=profile(client,token)['email']
    reset_request(client,email);reset_request(client,email)
    codes=[row['code'] for row in messages(inbox)]
    passwords=['first competing new password','second competing new password']
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda pair:confirm(client,*pair),zip(codes,passwords)))
    assert sorted(result.status_code for result in results)==[204,400]
    outcomes=[client.post('/api/v1/auth/login',json={'email':email,'password':password}).status_code for password in passwords]
    assert sorted(outcomes)==[200,401]


def test_deleted_account_code_cannot_recover_reregistered_email(client,inbox):
    token=new_user(client);me=profile(client,token);reset_request(client,me['email']);code=latest(inbox,'reset')
    assert client.post('/api/v1/account/delete',headers=headers(token),json={'current_password':PASSWORD,'receipt_key':str(uuid.uuid4())}).status_code==202
    new=client.post('/api/v1/auth/register',json={'email':me['email'],'password':NEW});assert new.status_code==201
    assert confirm(client,code).status_code==400
    assert profile(client,new.json()['access_token'])['id']!=me['id']


def test_request_limits_apply_to_unknown_email_and_are_generic(client,inbox,monkeypatch):
    monkeypatch.setattr(get_settings(),'auth_action_email_limit',1)
    address='absent-'+uuid.uuid4().hex+'@example.com'
    assert reset_request(client,address).status_code==202
    denied=reset_request(client,address)
    assert denied.status_code==429 and denied.headers.get('retry-after')
    assert not messages(inbox)


def test_delivery_failure_does_not_expose_account_or_log_credentials(client,inbox,monkeypatch,caplog):
    token=new_user(client);email=profile(client,token)['email']
    def fail(*args):raise OSError('private-email-and-token')
    monkeypatch.setattr('app.auth_actions.write_local_message',fail)
    response=reset_request(client,email)
    assert response.status_code==202 and response.json()=={'status':'accepted'}
    assert 'private-email-and-token' not in caplog.text and email not in caplog.text
    with SessionLocal() as db:
        assert all(row.used_at for row in db.scalars(select(AuthAction).where(AuthAction.user_id==profile(client,token)['id'])))


def test_auth_validation_never_echoes_password_or_action_code(client,inbox):
    code='private-incomplete-code';password='tiny-secret'
    response=client.post('/api/v1/auth/password-reset/confirm',json={'code':code,'new_password':password})
    assert response.status_code==422 and code not in response.text and password not in response.text
    response=client.post('/api/v1/auth/register',json={'email':'bad-email','password':password})
    assert response.status_code==422 and password not in response.text and 'bad-email' not in response.text


@pytest.mark.parametrize('environment',['staging','production'])
def test_file_delivery_cannot_be_enabled_outside_local_development(monkeypatch,environment):
    monkeypatch.setenv('AUTH_MAIL_BACKEND','file');monkeypatch.setenv('APP_ENV',environment)
    with pytest.raises(RuntimeError,match='forbidden'):Settings()


def test_private_mail_refuses_symlink_and_broad_permissions(client,inbox,monkeypatch,tmp_path):
    token=new_user(client);email=profile(client,token)['email']
    if os.name=='posix':
        inbox.mkdir(mode=0o755);inbox.chmod(0o755)
        assert reset_request(client,email).status_code==202 and not messages(inbox)
        inbox.rmdir()
        outside=tmp_path/'outside';outside.mkdir();inbox.symlink_to(outside,target_is_directory=True)
        assert reset_request(client,email).status_code==202 and not list(outside.iterdir())
        inbox.unlink()
    else:
        # Windows ACL enforcement is an operator prerequisite, not POSIX mode proof.
        assert reset_request(client,email).status_code==202


def test_expired_action_cleanup_keeps_valid_proofs(client,inbox):
    from app.auth_limits import cleanup_auth
    token=new_user(client);uid=profile(client,token)['id'];email=profile(client,token)['email']
    reset_request(client,email);first=latest(inbox,'reset');reset_request(client,email);second=latest(inbox,'reset')
    assert first!=second
    with SessionLocal.begin() as db:
        db.scalar(select(AuthAction).where(AuthAction.token_hash==token_hash(first))).expires_at=utcnow()-timedelta(seconds=1)
    cleanup_auth()
    with SessionLocal() as db:
        assert not db.scalar(select(AuthAction).where(AuthAction.token_hash==token_hash(first)))
        assert db.scalar(select(AuthAction).where(AuthAction.token_hash==token_hash(second)))
    assert confirm(client,second).status_code==204


def test_local_message_is_published_only_after_action_commit(client,inbox,monkeypatch):
    from app.auth_mail import write_local_message
    def committed(action,recipient,code):
        with SessionLocal() as db:
            row=db.get(AuthAction,action.id)
            assert row and row.token_hash==token_hash(code)
        return write_local_message(action,recipient,code)
    monkeypatch.setattr('app.auth_actions.write_local_message',committed)
    token=new_user(client);email=profile(client,token)['email']
    assert reset_request(client,email).status_code==202 and len(messages(inbox))==1
    assert confirm(client,latest(inbox,'reset')).status_code==204
