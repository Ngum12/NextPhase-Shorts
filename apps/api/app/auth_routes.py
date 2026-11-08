"""First auth-hardening slice: revocable sessions, bounded login and password change."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field, ConfigDict, UUID4
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .auth import AuthContext, DUMMY_HASH, current_auth, unauthorized, make_password_hash, verify_password
from .auth_limits import consume_limits
from .auth_action_tokens import invalidate_actions
from .config import get_settings
from .db import session_dep
from .models import AuthSession, User, utcnow
from .queue import lock_owner
from .schemas import RegisterRequest, TokenResponse
from .refresh import issue_pair, rotate, revoke_families, revoke_by_refresh, digest

router = APIRouter(prefix='/api/v1/auth', tags=['authentication'])


def peer(request):
    # No X-Forwarded-For parsing here. Uvicorn must use --no-proxy-headers unless
    # an operator configures a trusted, sanitized reverse-proxy boundary.
    return request.client.host if request.client else 'unknown'


def token_result(user_id, db, response):
    tokens = issue_pair(db, user_id)
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    return TokenResponse(**tokens)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    refresh_token: str = Field(min_length=43, max_length=43, pattern=r'^[A-Za-z0-9_-]{43}$')


class RotationRequest(RefreshRequest):
    rotation_key: UUID4


def refresh_limit(request, raw):
    consume_limits([('refresh-ip', peer(request), get_settings().auth_refresh_ip_limit),
                    ('refresh-token', digest('refresh-rate', raw), 20)])


@router.post('/refresh', response_model=TokenResponse)
def refresh(payload: RotationRequest, request: Request, response: Response, db: Session = Depends(session_dep)):
    refresh_limit(request, payload.refresh_token)
    tokens = rotate(db, payload.refresh_token, str(payload.rotation_key))
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    return tokens


@router.post('/refresh/logout', status_code=204)
def refresh_logout(payload: RefreshRequest, request: Request, db: Session = Depends(session_dep)):
    refresh_limit(request, payload.refresh_token)
    revoke_by_refresh(db, payload.refresh_token)
    db.commit()
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})


@router.post('/register', response_model=TokenResponse, status_code=201)
def register(data: RegisterRequest, request: Request, response: Response, db: Session = Depends(session_dep)):
    settings = get_settings()
    consume_limits([('register-ip', peer(request), settings.auth_register_ip_limit)])
    user = User(email=str(data.email).strip().lower(), password_hash=make_password_hash(data.password))
    try:
        db.add(user)
        db.flush()
        return token_result(user.id, db, response)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'An account with this email already exists')


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


@router.post('/login', response_model=TokenResponse)
def login(data: LoginRequest, request: Request, response: Response, db: Session = Depends(session_dep)):
    settings = get_settings()
    email = str(data.email).strip().lower()
    consume_limits([('login-ip', peer(request), settings.auth_login_ip_limit),
                    ('login-account', email, settings.auth_login_account_limit)])
    user = db.scalar(select(User).where(User.email == email))
    if user:
        lock_owner(db, user.id)
        db.refresh(user)  # Serialize with password changes; don't issue from a stale hash.
    verified = verify_password(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not verified:
        db.rollback()
        raise HTTPException(401, 'Incorrect email or password')
    return token_result(user.id, db, response)


@router.post('/logout', status_code=204)
def logout(auth: AuthContext = Depends(current_auth), db: Session = Depends(session_dep)):
    lock_owner(db, auth.user.id)
    if auth.session.family_id:
        revoke_families(db, auth.user.id, auth.session.family_id)
    else:
        from .restore_journal import record
        record('revoke',auth.user.id)
    db.execute(update(AuthSession).where(AuthSession.id == auth.session.id,
        AuthSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    db.commit()
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})


@router.post('/logout-all', status_code=204)
def logout_all(auth: AuthContext = Depends(current_auth), db: Session = Depends(session_dep)):
    lock_owner(db, auth.user.id)
    revoke_families(db, auth.user.id)
    db.execute(update(AuthSession).where(AuthSession.user_id == auth.user.id,
        AuthSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    db.commit()
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


@router.post('/password', status_code=204)
def change_password(data: PasswordChange, request: Request, auth: AuthContext = Depends(current_auth),
                    db: Session = Depends(session_dep)):
    settings = get_settings()
    consume_limits([('password-ip', peer(request), settings.auth_login_ip_limit),
                    ('password-account', auth.user.id, settings.auth_password_limit)])
    lock_owner(db, auth.user.id)
    db.refresh(auth.user)
    session = db.scalar(select(AuthSession).where(AuthSession.id == auth.session.id,
        AuthSession.revoked_at.is_(None), AuthSession.expires_at > utcnow()))
    if session is None:
        raise unauthorized()
    if not verify_password(data.current_password, auth.user.password_hash):
        db.rollback()
        raise HTTPException(400, 'Current password is incorrect')
    from .restore_journal import record
    record('password',auth.user.id)
    auth.user.password_hash = make_password_hash(data.new_password)
    invalidate_actions(db,auth.user.id)
    revoke_families(db,auth.user.id)
    db.execute(update(AuthSession).where(AuthSession.user_id == auth.user.id,
        AuthSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    db.commit()
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})
