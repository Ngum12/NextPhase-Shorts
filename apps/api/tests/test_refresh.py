import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import jwt
import pytest
from sqlalchemy import select, update, delete
from app.auth import make_token, AUDIENCE
from app.auth_limits import cleanup_auth
from app.config import get_settings
from app.db import SessionLocal
from app.models import AuthSession, RefreshFamily, RefreshGrant, AuthRateBucket, User, utcnow
from app.refresh import digest

PASSWORD='refresh-test-long-password'


def account(client):
    email=uuid.uuid4().hex+'@example.com'
    response=client.post('/api/v1/auth/register',json={'email':email,'password':PASSWORD})
    assert response.status_code==201
    return email,response.json()


def rotate(client,pair,key=None):
    return client.post('/api/v1/auth/refresh',json={'refresh_token':pair['refresh_token'],'rotation_key':key or str(uuid.uuid4())})


def headers(pair):return {'Authorization':'Bearer '+pair['access_token']}


@pytest.fixture(autouse=True)
def refresh_budget(monkeypatch):
    monkeypatch.setattr(get_settings(),'auth_refresh_ip_limit',10000)


def test_rotation_and_same_request_recovery_stores_no_plaintext(client):
    _,first=account(client);key=str(uuid.uuid4())
    response=rotate(client,first,key);assert response.status_code==200
    second=response.json();assert second['refresh_token']!=first['refresh_token']
    assert response.headers['cache-control']=='no-store'
    replay=rotate(client,first,key);assert replay.status_code==200
    assert replay.json()['access_token']==second['access_token']
    assert replay.json()['refresh_token']==second['refresh_token']
    claims=jwt.decode(second['access_token'],get_settings().jwt_secret,algorithms=['HS256'],audience=AUDIENCE)
    assert claims['exp']-claims['iat']<=900
    with SessionLocal() as db:
        grants=db.scalars(select(RefreshGrant).where(RefreshGrant.family_id==db.get(RefreshGrant,digest('refresh-store',first['refresh_token'])).family_id)).all()
        assert len(grants)==2
        assert all(row.token_hash not in (first['refresh_token'],second['refresh_token']) for row in grants)
        assert sum(row.used_at is not None for row in grants)==1
    assert client.get('/api/v1/me',headers=headers(first)).status_code==200
    assert client.get('/api/v1/me',headers=headers(second)).status_code==200


def test_reuse_revokes_entire_family_commits_and_preserves_other_login(client):
    email,first=account(client)
    other=client.post('/api/v1/auth/login',json={'email':email,'password':PASSWORD}).json()
    second=rotate(client,first).json()
    assert rotate(client,first).status_code==401
    assert client.get('/api/v1/me',headers=headers(first)).status_code==401
    assert client.get('/api/v1/me',headers=headers(second)).status_code==401
    assert rotate(client,second).status_code==401
    assert rotate(client,other).status_code==200


@pytest.mark.parametrize('same_key',[True,False])
def test_concurrent_rotations_are_serialized(client,same_key):
    _,first=account(client);key=str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda k:rotate(client,first,k),[key,key if same_key else str(uuid.uuid4())]))
    if same_key:
        assert [r.status_code for r in results]==[200,200]
        assert results[0].json()['refresh_token']==results[1].json()['refresh_token']
    else:
        assert sorted(r.status_code for r in results)==[200,401]
        success=next(r.json() for r in results if r.status_code==200)
        assert client.get('/api/v1/me',headers=headers(success)).status_code==401


def test_delayed_same_key_retry_does_not_revoke_newer_session(client):
    _,first=account(client);key=str(uuid.uuid4());second=rotate(client,first,key).json()
    third=rotate(client,second).json()
    assert rotate(client,first,key).status_code==401
    assert client.get('/api/v1/me',headers=headers(third)).status_code==200
    _,fresh=account(client);key=str(uuid.uuid4());next_pair=rotate(client,fresh,key).json()
    with SessionLocal.begin() as db:
        db.get(RefreshGrant,digest('refresh-store',fresh['refresh_token'])).used_at=utcnow()-timedelta(minutes=10)
    assert rotate(client,fresh,key).status_code==401
    assert client.get('/api/v1/me',headers=headers(next_pair)).status_code==200


@pytest.mark.parametrize('scope',['logout','logout-all','password','refresh/logout','delete'])
def test_all_revocation_paths_cover_refresh(client,scope):
    email,first=account(client)
    other=client.post('/api/v1/auth/login',json={'email':email,'password':PASSWORD}).json()
    second=rotate(client,first).json()
    if scope=='delete':
        response=client.post('/api/v1/account/delete',headers=headers(second),json={'current_password':PASSWORD,'receipt_key':str(uuid.uuid4())})
        assert response.status_code==202
    else:
        payload={'current_password':PASSWORD,'new_password':'new-long-refresh-password'} if scope=='password' else {'refresh_token':first['refresh_token']} if scope=='refresh/logout' else None
        response=client.post('/api/v1/auth/'+scope,headers=headers(second),json=payload)
        assert response.status_code==204
    assert rotate(client,second).status_code==401
    assert client.get('/api/v1/me',headers=headers(first)).status_code==401
    assert rotate(client,other).status_code==(200 if scope in ('logout','refresh/logout') else 401)


@pytest.mark.parametrize('kind',['idle','absolute','access'])
def test_expiries_and_refresh_after_access_expiry(client,kind):
    _,first=account(client)
    with SessionLocal.begin() as db:
        grant=db.get(RefreshGrant,digest('refresh-store',first['refresh_token']))
        if kind=='idle':grant.expires_at=utcnow()-timedelta(seconds=1)
        elif kind=='absolute':db.get(RefreshFamily,grant.family_id).expires_at=utcnow()-timedelta(seconds=1)
        else:db.execute(update(AuthSession).where(AuthSession.family_id==grant.family_id).values(expires_at=utcnow()-timedelta(seconds=1)))
    assert rotate(client,first).status_code==(200 if kind=='access' else 401)


def test_legacy_session_survives_and_refresh_validation_does_not_echo_secrets(client):
    email,_=account(client)
    with SessionLocal.begin() as db:
        uid=db.scalar(select(User.id).where(User.email==email));legacy=make_token(uid,db)
    assert client.get('/api/v1/me',headers={'Authorization':'Bearer '+legacy}).status_code==200
    secret='secret-value-not-to-echo'
    response=client.post('/api/v1/auth/refresh',json={'refresh_token':secret,'rotation_key':secret})
    assert response.status_code==422 and secret not in response.text
    assert rotate(client,{'refresh_token':'a'*43}).status_code==401


def test_refresh_rate_limit_and_cleanup_retains_consumed_tombstones(client,monkeypatch):
    _,first=account(client);rotate(client,first)
    with SessionLocal() as db:family_id=db.get(RefreshGrant,digest('refresh-store',first['refresh_token'])).family_id
    cleanup_auth()
    with SessionLocal() as db:assert db.get(RefreshGrant,digest('refresh-store',first['refresh_token'])) is not None
    monkeypatch.setattr(get_settings(),'auth_refresh_ip_limit',1)
    with SessionLocal.begin() as db:db.execute(delete(AuthRateBucket))
    assert rotate(client,{'refresh_token':'b'*43}).status_code==401
    limited=rotate(client,{'refresh_token':'c'*43});assert limited.status_code==429 and limited.headers['retry-after']
    with SessionLocal.begin() as db:db.get(RefreshFamily,family_id).expires_at=utcnow()-timedelta(seconds=1)
    cleanup_auth()
    with SessionLocal() as db:
        assert db.get(RefreshFamily,family_id) is None
        assert db.scalar(select(RefreshGrant).where(RefreshGrant.family_id==family_id)) is None
