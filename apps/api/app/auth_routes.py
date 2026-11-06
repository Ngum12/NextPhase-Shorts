"""First auth-hardening slice: revocable sessions, bounded login and password change."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .auth import AuthContext, DUMMY_HASH, current_auth, unauthorized, make_password_hash, make_token, verify_password
from .auth_limits import consume_limits
from .config import get_settings
from .db import session_dep
from .models import AuthSession, User, utcnow
from .queue import lock_owner
from .schemas import RegisterRequest, TokenResponse

router = APIRouter(prefix='/api/v1/auth', tags=['authentication'])


def peer(request):
    # No X-Forwarded-For parsing here. Uvicorn must use --no-proxy-headers unless
    # an operator configures a trusted, sanitized reverse-proxy boundary.
    return request.client.host if request.client else 'unknown'


def token_result(user_id, db, response):
    token = make_token(user_id, db)
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    return TokenResponse(access_token=token, expires_in=get_settings().auth_session_hours*3600)


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
    db.execute(update(AuthSession).where(AuthSession.id == auth.session.id,
        AuthSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    db.commit()
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})


@router.post('/logout-all', status_code=204)
def logout_all(auth: AuthContext = Depends(current_auth), db: Session = Depends(session_dep)):
    lock_owner(db, auth.user.id)
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
    auth.user.password_hash = make_password_hash(data.new_password)
    db.execute(update(AuthSession).where(AuthSession.user_id == auth.user.id,
        AuthSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    db.commit()
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})
