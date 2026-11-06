import hashlib
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, update
from app.auth import AUDIENCE, ISSUER, make_password_hash
from app.auth_limits import cleanup_auth, consume_limits
from app.config import get_settings
from app.db import SessionLocal
from app.models import AuthRateBucket, AuthSession, User, utcnow

PASSWORD='original-long-password'
def account(client):
    email=f'auth-{uuid.uuid4().hex}@example.com'
    response=client.post('/api/v1/auth/register',json={'email':email,'password':PASSWORD})
    assert response.status_code==201
    return email,response.json()['access_token']
def headers(token):return {'Authorization':f'Bearer {token}'}
def login(client,email,password=PASSWORD):
    return client.post('/api/v1/auth/login',json={'email':email,'password':password})
def me(client,token):return client.get('/api/v1/me',headers=headers(token))


def test_session_metadata_and_hashed_storage(client):
    email,token=account(client)
    response=login(client,email)
    assert response.status_code==200
    assert response.headers['cache-control']=='no-store'
    assert response.headers['pragma']=='no-cache'
    assert response.json()['expires_in']==get_settings().auth_session_hours*3600
    claims=jwt.decode(token,get_settings().jwt_secret,algorithms=['HS256'],audience=AUDIENCE,issuer=ISSUER)
    with SessionLocal() as db:
        session=db.get(AuthSession,hashlib.sha256(claims['jti'].encode()).hexdigest())
        assert session and session.user_id==claims['sub']
        assert token not in session.id and claims['jti']!=session.id
    assert me(client,token).status_code==200


def test_logout_scope_and_logout_all_durable(client):
    email,first=account(client);second=login(client,email).json()['access_token']
    _,other=account(client)
    assert client.post('/api/v1/auth/logout',headers=headers(first)).status_code==204
    assert me(client,first).status_code==401
    assert me(client,second).status_code==200
    assert client.post('/api/v1/auth/logout-all',headers=headers(second)).status_code==204
    assert me(client,second).status_code==401
    assert me(client,other).status_code==200
    assert login(client,email).status_code==200


def test_password_change_checks_current_and_revokes_every_session(client):
    email,first=account(client);second=login(client,email).json()['access_token']
    endpoint='/api/v1/auth/password'
    assert client.post(endpoint,headers=headers(first),json={'current_password':'wrong','new_password':'replacement-password'}).status_code==400
    assert me(client,first).status_code==200
    assert client.post(endpoint,headers=headers(first),json={'current_password':PASSWORD,'new_password':'too-short'}).status_code==422
    assert client.post(endpoint,headers=headers(first),json={'current_password':PASSWORD,'new_password':'replacement-password'}).status_code==204
    assert me(client,first).status_code==me(client,second).status_code==401
    assert login(client,email).status_code==401
    assert login(client,email,'replacement-password').status_code==200


def test_existing_short_password_and_unknown_email_response(client,monkeypatch):
    email=f'legacy-{uuid.uuid4().hex}@example.com'
    with SessionLocal.begin() as db:db.add(User(email=email,password_hash=make_password_hash('1234567890')))
    assert login(client,email,'1234567890').status_code==200
    assert login(client,email,'wrong').json()==login(client,'missing@example.com','wrong').json()
    import app.auth_routes as routes
    real=routes.verify_password;hashes=[]
    def verify(password,saved):hashes.append(saved);return real(password,saved)
    monkeypatch.setattr(routes,'verify_password',verify)
    assert login(client,f'{uuid.uuid4().hex}@example.com','wrong').status_code==401
    assert hashes==[routes.DUMMY_HASH]
    assert client.post('/api/v1/auth/register',json={'email':'weak@example.com','password':'1234567890'}).status_code==422


@pytest.mark.parametrize('change',[
    {'aud':'wrong'},{'iss':'wrong'},{'jti':'short'},{'jti':'x'*32},{'sub':'other-user'},
    {'exp':0},{'iat':4102444800},{'aud':None},{'jti':None},
])
def test_tampered_or_legacy_claims_rejected(client,change):
    _,token=account(client)
    claims=jwt.decode(token,get_settings().jwt_secret,algorithms=['HS256'],audience=AUDIENCE)
    for key,value in change.items():
        if value is None:claims.pop(key)
        else:claims[key]=value
    encoded=jwt.encode(claims,get_settings().jwt_secret,algorithm='HS256')
    response=me(client,encoded)
    assert response.status_code==401
    assert response.headers['www-authenticate']=='Bearer'


def test_database_expiry_and_cleanup(client):
    _,token=account(client)
    claims=jwt.decode(token,get_settings().jwt_secret,algorithms=['HS256'],audience=AUDIENCE)
    key=hashlib.sha256(claims['jti'].encode()).hexdigest()
    with SessionLocal.begin() as db:db.execute(update(AuthSession).where(AuthSession.id==key).values(expires_at=utcnow()-timedelta(seconds=1)))
    assert me(client,token).status_code==401
    cleanup_auth()
    with SessionLocal() as db:assert db.get(AuthSession,key) is None


@pytest.fixture
def limited(monkeypatch):
    with SessionLocal.begin() as db:db.execute(delete(AuthRateBucket))
    settings=get_settings()
    for name in ('auth_login_account_limit','auth_login_ip_limit','auth_register_ip_limit','auth_password_limit'):
        monkeypatch.setattr(settings,name,2)
    return settings


def test_account_limit_survives_denial_and_ignores_forwarded_ip(client,limited):
    email,token=account(client)
    assert login(client,email,'wrong').status_code==401
    assert login(client,email.upper(),'wrong').status_code==401
    response=client.post('/api/v1/auth/login',json={'email':email,'password':PASSWORD},headers={'X-Forwarded-For':'203.0.113.9'})
    assert response.status_code==429 and int(response.headers['retry-after'])>0
    assert login(client,email).status_code==429
    assert me(client,token).status_code==200
    with SessionLocal() as db:
        rows=db.scalars(select(AuthRateBucket)).all()
        assert all(len(row.key)==64 and email not in row.key for row in rows)
        assert any(row.attempts==3 for row in rows)


def test_ip_registration_and_password_limits_and_reset(client,limited):
    limited.auth_login_ip_limit=100
    email,token=account(client)
    account(client)
    response=client.post('/api/v1/auth/register',json={'email':'blocked@example.com','password':PASSWORD})
    assert response.status_code==429
    for _ in range(2):assert client.post('/api/v1/auth/password',headers=headers(token),json={'current_password':'wrong','new_password':PASSWORD}).status_code==400
    assert client.post('/api/v1/auth/password',headers=headers(token),json={'current_password':PASSWORD,'new_password':PASSWORD}).status_code==429
    with SessionLocal.begin() as db:db.execute(update(AuthRateBucket).values(expires_at=utcnow()-timedelta(seconds=1)))
    assert login(client,email).status_code==200
    account(client)


def test_login_ip_budget_across_unknown_accounts(client,limited):
    for _ in range(2):assert login(client,f'{uuid.uuid4().hex}@example.com').status_code==401
    assert login(client,f'{uuid.uuid4().hex}@example.com').status_code==429


def test_concurrent_atomic_limits(limited):
    identity=uuid.uuid4().hex
    def attempt(_):
        try:consume_limits([('concurrency',identity,2)]);return 200
        except HTTPException as error:return error.status_code
    with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(attempt,range(6)))
    assert sorted(results)==[200,200,429,429,429,429]


@pytest.mark.parametrize('expired', [False, True])
def test_revocation_between_authentication_and_password_lock_is_rechecked(client,monkeypatch,expired):
    email,token=account(client)
    import app.auth_routes as routes
    original=routes.consume_limits
    def revoke_during_limits(identities):
        original(identities)
        with SessionLocal.begin() as db:
            user=db.scalar(select(User).where(User.email==email))
            values={'expires_at':utcnow()-timedelta(seconds=1)} if expired else {'revoked_at':utcnow()}
            db.execute(update(AuthSession).where(AuthSession.user_id==user.id).values(**values))
    monkeypatch.setattr(routes,'consume_limits',revoke_during_limits)
    result=client.post('/api/v1/auth/password',headers=headers(token),
        json={'current_password':PASSWORD,'new_password':'replacement-password'})
    assert result.status_code==401
    monkeypatch.setattr(routes,'consume_limits',original)
    assert login(client,email).status_code==200
