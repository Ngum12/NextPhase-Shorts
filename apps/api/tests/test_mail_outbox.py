import json
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select,update,delete,func
from app import mail_outbox as box,mail_transport as transport
from app.auth_limits import cleanup_auth
from app.config import get_settings,Settings
from app.db import SessionLocal
from app.models import AuthAction,AuthSession,MailOutbox,MailBudget,User,utcnow

PASSWORD='mail-tests-private-password'


@pytest.fixture
def mail(monkeypatch):
    settings=get_settings()
    values={'auth_mail_backend':'resend','auth_mail_send_enabled':True,'resend_api_key':'re_synthetic-key-never-valid',
        'auth_mail_keys':[Fernet.generate_key().decode()],'auth_mail_from':'noreply@auth.example.com',
        'auth_mail_recipients':(),'auth_mail_daily_limit':20,'auth_mail_monthly_limit':500,
        'auth_require_verified_email':False,'auth_action_email_limit':20}
    for key,value in values.items():monkeypatch.setattr(settings,key,value)
    with SessionLocal.begin() as db:
        db.execute(update(MailOutbox).values(state='cancelled',payload=None,lease_token=None,lease_until=None))
        db.execute(delete(MailBudget))
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'id':str(uuid.uuid4())})
    monkeypatch.setattr(transport,'make_client',lambda:httpx.Client(transport=httpx.MockTransport(handler)))
    return settings,calls


def account(client,mail):
    email=uuid.uuid4().hex+'@example.com'
    mail[0].auth_mail_recipients=(*mail[0].auth_mail_recipients,email)
    response=client.post('/api/v1/auth/register',json={'email':email,'password':PASSWORD})
    assert response.status_code==201
    pair=response.json();headers={'Authorization':'Bearer '+pair['access_token']}
    uid=client.get('/api/v1/me',headers=headers).json()['id']
    return email,uid,headers,pair


def request(client,headers):
    response=client.post('/api/v1/auth/email-verification/request',headers=headers)
    assert response.status_code==202
    return response


def row_for(owner):
    with SessionLocal() as db:
        row=db.scalar(select(MailOutbox).where(MailOutbox.user_id==owner).order_by(MailOutbox.created_at.desc()))
        envelope=json.loads(box.cipher().decrypt(row.payload.encode())) if row.payload else None
        return row,envelope


def due(identity):
    with SessionLocal.begin() as db:
        db.execute(update(MailOutbox).where(MailOutbox.id==identity).values(due_at=utcnow()-timedelta(seconds=1)))
        db.execute(update(MailBudget).values(next_send_at=utcnow()-timedelta(seconds=1)))


def test_action_outbox_atomic_encrypted_and_provider_acceptance_before_confirm(client,mail):
    email,uid,headers,_=account(client,mail);response=request(client,headers)
    row,envelope=row_for(uid)
    assert row.state=='pending' and email not in row.payload and envelope['code'] not in row.payload
    assert envelope['code'] not in response.text and email not in response.text
    with SessionLocal() as db:
        action=db.get(AuthAction,row.action_id)
        assert action.delivery_method=='resend' and action.token_hash==box.token_hash(envelope['code'])
    payload={'code':envelope['code']}
    assert client.post('/api/v1/auth/email-verification/confirm',json=payload).status_code==400
    assert box.dispatch_one()
    accepted,_=row_for(uid);assert accepted.state=='accepted' and accepted.payload is None
    assert client.post('/api/v1/auth/email-verification/confirm',json=payload).status_code==204
    profile=client.get('/api/v1/me',headers=headers).json()
    assert profile['email_verification_method']=='resend' and profile['email_verified_at']
    assert client.post('/api/v1/auth/email-verification/confirm',json=payload).status_code==400
    sent=mail[1][0]
    assert str(sent.url)=='https://api.resend.com/emails'
    assert sent.headers['idempotency-key']=='auth-'+row.id
    assert sent.headers['authorization']=='Bearer '+mail[0].resend_api_key
    assert json.loads(sent.content)==envelope['message']


def test_unknown_reset_uniform_and_encryption_failure_rolls_back_without_leak(client,mail,monkeypatch,caplog):
    email,uid,headers,_=account(client,mail)
    class Broken:
        def encrypt(self,_):raise ValueError('private-sensitive-content')
    monkeypatch.setattr(box,'cipher',lambda:Broken())
    known=client.post('/api/v1/auth/password-reset/request',json={'email':email})
    unknown=client.post('/api/v1/auth/password-reset/request',json={'email':'absent@example.com'})
    assert known.status_code==unknown.status_code==202 and known.json()==unknown.json()=={'status':'accepted'}
    assert email not in caplog.text and 'private-sensitive-content' not in caplog.text
    with SessionLocal() as db:
        assert not db.scalar(select(AuthAction.id).where(AuthAction.user_id==uid))
        assert not db.scalar(select(MailOutbox.id).where(MailOutbox.user_id==uid))


@pytest.mark.parametrize('status,retry',[(429,True),(500,True),(409,True),(400,False),(401,False),(403,False),(302,False)])
def test_provider_failures_are_bounded_safe_and_retryable(client,mail,monkeypatch,status,retry):
    email,uid,headers,_=account(client,mail);request(client,headers);row,envelope=row_for(uid)
    calls=[]
    def handler(req):
        calls.append(req);return httpx.Response(status,headers={'Retry-After':'240'},json={'detail':email+envelope['code']})
    monkeypatch.setattr(transport,'make_client',lambda:httpx.Client(transport=httpx.MockTransport(handler)))
    assert box.dispatch_one();result,_=row_for(uid)
    assert result.state==('retry' if retry else 'failed')
    assert email not in result.last_code and envelope['code'] not in result.last_code
    if status==429:assert box.aware(result.due_at)>=utcnow()+timedelta(seconds=230)
    if retry:
        due(row.id);assert box.dispatch_one();assert calls[0].headers['idempotency-key']==calls[1].headers['idempotency-key']
        assert calls[0].content==calls[1].content
    else:assert result.payload is None


def test_network_failure_then_retry_keeps_one_logical_message(client,mail,monkeypatch):
    _,uid,headers,_=account(client,mail);request(client,headers);row,_=row_for(uid)
    calls=[]
    def handler(req):
        calls.append(req)
        if len(calls)==1:raise httpx.ReadTimeout('synthetic secret must not be logged')
        return httpx.Response(200,json={'id':str(uuid.uuid4())})
    monkeypatch.setattr(transport,'make_client',lambda:httpx.Client(transport=httpx.MockTransport(handler)))
    assert box.dispatch_one();assert row_for(uid)[0].state=='retry'
    due(row.id);assert box.dispatch_one();assert row_for(uid)[0].state=='accepted'
    assert calls[0].content==calls[1].content and calls[0].headers['idempotency-key']==calls[1].headers['idempotency-key']


def test_competing_workers_only_claim_once_and_stale_completion_is_fenced(client,mail,monkeypatch):
    _,uid,headers,_=account(client,mail);request(client,headers)
    with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(lambda _:box.claim(),range(2)))
    assert sum(work is not None for work in claims)==1;first=next(work for work in claims if work)
    with SessionLocal.begin() as db:
        db.get(MailOutbox,first['id']).lease_until=utcnow()-timedelta(seconds=1)
    due(first['id']);second=box.claim();assert second and second['token']!=first['token']
    monkeypatch.setattr(box,'claim',lambda:first);box.dispatch_one()
    assert row_for(uid)[0].lease_token==second['token'] and row_for(uid)[0].state=='sending'
    monkeypatch.setattr(box,'claim',lambda:second);box.dispatch_one();assert row_for(uid)[0].state=='accepted'


@pytest.mark.parametrize('operation',['password','delete'])
def test_account_mutation_cancels_queued_delivery_and_scrubs_payload(client,mail,operation):
    _,uid,headers,_=account(client,mail);request(client,headers)
    if operation=='password':
        result=client.post('/api/v1/auth/password',headers=headers,json={'current_password':PASSWORD,'new_password':'replacement-password-long'})
        assert result.status_code==204
    else:
        result=client.post('/api/v1/account/delete',headers=headers,json={'current_password':PASSWORD,'receipt_key':str(uuid.uuid4())})
        assert result.status_code==202
    row,_=row_for(uid);assert row.state=='cancelled' and row.payload is None
    assert not box.dispatch_one() and not mail[1]


def test_deletion_during_provider_call_cannot_be_overwritten_by_acceptance(client,mail,monkeypatch):
    _,uid,headers,_=account(client,mail);request(client,headers)
    def send(*_):
        assert client.post('/api/v1/account/delete',headers=headers,json={'current_password':PASSWORD,'receipt_key':str(uuid.uuid4())}).status_code==202
    monkeypatch.setattr(transport,'send',send)
    assert box.dispatch_one();assert row_for(uid)[0].state=='cancelled'


def test_daily_monthly_budgets_and_throttle_are_shared_and_conservative(client,mail):
    _,uid,headers,_=account(client,mail);request(client,headers)
    assert box.dispatch_one()
    request(client,headers);row,_=row_for(uid)
    with SessionLocal.begin() as db:db.get(MailBudget,'resend').next_send_at=utcnow()+timedelta(seconds=30)
    assert not box.dispatch_one();assert row_for(uid)[0].last_code=='local_throttle'
    due(row.id);mail[0].auth_mail_daily_limit=1
    assert not box.dispatch_one();assert row_for(uid)[0].last_code=='local_quota'
    assert len(mail[1])==1
    with SessionLocal.begin() as db:
        budget=db.get(MailBudget,'resend');budget.day='2000-01-01';budget.monthly_attempts=500
    due(row.id);assert not box.dispatch_one();assert row_for(uid)[0].last_code=='local_quota'


def test_key_rotation_tamper_binding_and_expiry_cleanup(client,mail):
    _,uid,headers,_=account(client,mail);request(client,headers);row,envelope=row_for(uid)
    old=mail[0].auth_mail_keys[0];new=Fernet.generate_key().decode();mail[0].auth_mail_keys=[new,old]
    assert box.reencrypt_pending()=={'processed':1,'next_after':None}
    mail[0].auth_mail_keys=[new];assert row_for(uid)[1]['code']==envelope['code']
    with SessionLocal.begin() as db:db.get(MailOutbox,row.id).expires_at=utcnow()-timedelta(seconds=1)
    box.cleanup_mail();assert row_for(uid)[0].payload is None
    with SessionLocal.begin() as db:
        db.get(MailOutbox,row.id).expires_at=utcnow()-timedelta(days=2)
        db.get(AuthAction,row.action_id).expires_at=utcnow()-timedelta(days=2)
    cleanup_auth()
    with SessionLocal() as db:assert db.get(MailOutbox,row.id) is None and db.get(AuthAction,row.action_id) is None


@pytest.mark.parametrize('kind',['wrong_key','wrong_binding','malformed','expired','attempts'])
def test_invalid_pending_payloads_never_send(client,mail,kind):
    _,uid,headers,_=account(client,mail);request(client,headers);row,envelope=row_for(uid)
    with SessionLocal.begin() as db:
        current=db.get(MailOutbox,row.id)
        if kind=='wrong_key':mail[0].auth_mail_keys=[Fernet.generate_key().decode()]
        elif kind=='wrong_binding':
            envelope['owner']='another-owner';current.payload=box.cipher().encrypt(json.dumps(envelope).encode()).decode()
        elif kind=='malformed':current.payload='not-encrypted'
        elif kind=='expired':current.expires_at=utcnow()-timedelta(seconds=1)
        else:current.attempts=5
    assert not box.dispatch_one() and not mail[1]
    assert row_for(uid)[0].payload is None


def test_local_proof_does_not_satisfy_verified_upload_policy_and_reads_stay_available(client,mail):
    _,uid,headers,_=account(client,mail);mail[0].auth_require_verified_email=True
    with SessionLocal.begin() as db:
        user=db.get(User,uid);user.email_verified_at=utcnow();user.email_verification_method='local_file'
    payload={'file_name':'test.mp4','total_bytes':10,'title':'Test','style':'vlog','desired_seconds':15,'rights_confirmed':True,'consent_version':'upload-rights-v1'}
    root='/api/v1/upload-sessions';key={'Idempotency-Key':uuid.uuid4().hex}
    assert client.post(root,headers={**headers,**key},json=payload).status_code==403
    assert client.put(root+'/missing/parts?offset=0',headers={**headers,'X-Chunk-SHA256':'a'*64},content=b'a').status_code==403
    for suffix,data in [('complete',None),('part-url',{'offset':0,'sha256':'a'*64}),('part-commit/missing',None)]:
        assert client.post(root+'/missing/'+suffix,headers=headers,json=data).status_code==403
    assert client.post('/api/v1/jobs',headers=headers,files={'file':('a.mp4',b'not-video','video/mp4')},data={'title':'t','style':'vlog','desired_seconds':'15'}).status_code==403
    assert client.get('/api/v1/me',headers=headers).status_code==200
    assert client.get('/api/v1/jobs',headers=headers).status_code==200
    request(client,headers);row,envelope=row_for(uid);assert box.dispatch_one()
    assert client.post('/api/v1/auth/email-verification/confirm',json={'code':envelope['code']}).status_code==204
    response=client.post(root,headers={**headers,**key},json=payload);assert response.status_code==201
    assert client.post(root+'/'+response.json()['id']+'/abort',headers=headers).status_code==200


def test_real_reset_revokes_refresh_sessions_and_pending_messages(client,mail):
    email,uid,headers,pair=account(client,mail)
    assert client.post('/api/v1/auth/password-reset/request',json={'email':email}).status_code==202
    row,envelope=row_for(uid);assert box.dispatch_one()
    request(client,headers)  # A second queued action must be invalidated by reset.
    assert client.post('/api/v1/auth/password-reset/confirm',json={'code':envelope['code'],'new_password':'a-new-password-for-email-reset'}).status_code==204
    assert client.get('/api/v1/me',headers=headers).status_code==401
    assert client.post('/api/v1/auth/refresh',json={'refresh_token':pair['refresh_token'],'rotation_key':str(uuid.uuid4())}).status_code==401
    assert row_for(uid)[0].state=='cancelled'


def test_recipient_allowlist_and_disabled_switch_prevent_dispatch(client,mail):
    _,uid,headers,_=account(client,mail);request(client,headers)
    mail[0].auth_mail_send_enabled=False;assert not box.dispatch_one() and not mail[1]
    assert client.get('/api/v1/auth/recovery-capabilities').json()['delivery']=='disabled'
    mail[0].auth_mail_send_enabled=True;mail[0].auth_mail_recipients=()
    assert not box.dispatch_one();assert row_for(uid)[0].last_code=='recipient_not_allowed'


def test_owner_pending_admission_is_bounded(client,mail):
    email,uid,headers,_=account(client,mail)
    for _ in range(5):request(client,headers)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(MailOutbox).where(MailOutbox.user_id==uid))==3


def test_real_configuration_requires_explicit_switch_keys_recipient_and_separate_secret(monkeypatch):
    monkeypatch.setenv('AUTH_MAIL_BACKEND','resend');assert Settings().auth_mail_send_enabled is False
    monkeypatch.setenv('AUTH_MAIL_SEND_ENABLED','true')
    with pytest.raises(RuntimeError):Settings()
    key=Fernet.generate_key().decode()
    monkeypatch.setenv('AUTH_MAIL_FROM','noreply@auth.example.com');monkeypatch.setenv('RESEND_API_KEY','re_synthetic-server-secret')
    monkeypatch.setenv('AUTH_MAIL_ENCRYPTION_KEYS',key)
    with pytest.raises(RuntimeError,match='recipient allowlist'):Settings()
    monkeypatch.setenv('AUTH_MAIL_RECIPIENTS','owner@example.com');assert Settings().auth_mail_send_enabled
    monkeypatch.setenv('JWT_SECRET',key)
    with pytest.raises(RuntimeError,match='separate'):Settings()


def test_budget_clock_reversal_cannot_reset_counters(client,mail):
    _,uid,headers,_=account(client,mail);request(client,headers);box.dispatch_one();request(client,headers)
    row,_=row_for(uid);due(row.id)
    with SessionLocal.begin() as db:db.get(MailBudget,'resend').day='2999-01-01'
    assert not box.dispatch_one();assert row_for(uid)[0].last_code=='local_clock_skew'
    assert len(mail[1])==1


def test_failed_provider_reply_is_not_durable_acceptance_and_attempts_stop(client,mail,monkeypatch):
    _,uid,headers,_=account(client,mail);request(client,headers);row,_=row_for(uid)
    monkeypatch.setattr(transport,'make_client',lambda:httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'status':'maybe'}))))
    for _ in range(5):due(row.id);assert box.dispatch_one()
    result,_=row_for(uid);assert result.state=='failed' and result.attempts==5 and result.payload is None
    assert not box.dispatch_one()


def test_private_setup_helper_preserves_encryption_key_and_never_enables_sending(tmp_path,monkeypatch,capsys):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('email_setup',Path(__file__).resolve().parents[3]/'scripts/configure_auth_email.py')
    setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)
    monkeypatch.setattr(setup,'ROOT',tmp_path);monkeypatch.setattr(setup.sys.stdin,'isatty',lambda:True)
    monkeypatch.setattr(setup.getpass,'getpass',lambda _: 're_private-synthetic-api-key')
    for _ in range(2):
        answers=iter(['','owner@example.com']);monkeypatch.setattr('builtins.input',lambda _:next(answers));setup.main()
        config=json.loads((tmp_path/'.data/auth-email-env.json').read_text())
        assert config['AUTH_MAIL_SEND_ENABLED']=='false' and config['AUTH_REQUIRE_VERIFIED_EMAIL']=='false'
        if _==0:key=config['AUTH_MAIL_ENCRYPTION_KEYS']
        else:assert config['AUTH_MAIL_ENCRYPTION_KEYS']==key
    output=capsys.readouterr().out
    assert key not in output and config['RESEND_API_KEY'] not in output and 'owner@example.com' not in output
