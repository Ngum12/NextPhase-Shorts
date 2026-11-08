import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import timedelta
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import get_settings
from .db import session_dep
from .models import AuthSession, RefreshFamily, User, utcnow

bearer = HTTPBearer(auto_error=False)
ISSUER = 'nextphase-shorts'
AUDIENCE = 'nextphase-shorts-mobile'


def make_password_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return 'scrypt$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(digest).decode()


def verify_password(password: str, saved: str) -> bool:
    try:
        scheme, salt, digest = saved.split('$')
        if scheme != 'scrypt':
            return False
        computed = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(computed, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


DUMMY_HASH = make_password_hash('not-an-account-password')


def make_token(user_id: str, db: Session) -> str:
    now = utcnow()
    expiry = now + timedelta(hours=get_settings().auth_session_hours)
    nonce = secrets.token_urlsafe(32)
    db.add(AuthSession(id=hashlib.sha256(nonce.encode()).hexdigest(), user_id=user_id,
                       created_at=now, expires_at=expiry))
    return jwt.encode({'sub': user_id, 'jti': nonce, 'iat': now, 'exp': expiry,
                       'iss': ISSUER, 'aud': AUDIENCE}, get_settings().jwt_secret, algorithm='HS256')


@dataclass
class AuthContext:
    user: User
    session: AuthSession


def unauthorized():
    return HTTPException(401, 'Invalid or expired session. Sign in again.', headers={'WWW-Authenticate': 'Bearer', 'Cache-Control': 'no-store'})


def current_auth(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(session_dep)) -> AuthContext:
    if creds is None or len(creds.credentials) > 4096:
        raise unauthorized()
    try:
        claims = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=['HS256'],
            issuer=ISSUER, audience=AUDIENCE, options={'require': ['sub', 'jti', 'iat', 'exp', 'iss', 'aud']})
        nonce = claims['jti']
        if not isinstance(nonce, str) or not 16 <= len(nonce) <= 128:
            raise unauthorized()
        session_id = hashlib.sha256(nonce.encode()).hexdigest()
        result = db.execute(select(User, AuthSession).join(AuthSession, AuthSession.user_id == User.id).where(
            AuthSession.id == session_id, AuthSession.user_id == claims['sub'],
            User.deleted_at.is_(None),
            AuthSession.revoked_at.is_(None), AuthSession.expires_at > utcnow())).first()
        if result and result[1].family_id:
            family = db.scalar(select(RefreshFamily.id).where(RefreshFamily.id == result[1].family_id,
                RefreshFamily.user_id == result[0].id, RefreshFamily.revoked_at.is_(None), RefreshFamily.expires_at > utcnow()))
            if not family:
                raise unauthorized()
        if result:
            return AuthContext(*result)
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        pass
    raise unauthorized()


def current_user(auth: AuthContext = Depends(current_auth)) -> User:
    return auth.user


def upload_user(user: User = Depends(current_user)) -> User:
    # Recovery, sign-in, existing-project reads and deletion stay accessible.
    if get_settings().auth_require_verified_email and not (
            user.email_verified_at and user.email_verification_method=='resend'):
        raise HTTPException(403,'Confirm your email in Account before starting or resuming uploads.',
            headers={'Cache-Control':'no-store'})
    return user
