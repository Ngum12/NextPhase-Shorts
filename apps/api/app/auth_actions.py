"""Local-development proof flows. Real email delivery remains disabled/unimplemented."""
from datetime import timedelta,timezone
import hmac,logging,secrets
from fastapi import APIRouter,BackgroundTasks,Depends,HTTPException,Request,Response
from pydantic import BaseModel,EmailStr,Field,ConfigDict
from sqlalchemy import select,update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from .auth import AuthContext,current_auth,make_password_hash
from .auth_routes import peer
from .auth_action_tokens import account_digest,token_hash,invalidate_actions
from .auth_limits import consume_limits
from .auth_mail import write_local_message
from .config import get_settings
from .db import SessionLocal,session_dep
from .models import AuthAction,AuthSession,User,utcnow
from .queue import lock_owner
from .refresh import revoke_families

router=APIRouter(prefix='/api/v1/auth',tags=['local email actions'])
logger=logging.getLogger('nextphase.auth-actions')
INVALID='Invalid or expired code. Request a new one.'


def local_enabled():
    settings=get_settings()
    return settings.auth_mail_backend=='file' and settings.env in ('development','test')


def require_enabled():
    if not local_enabled():raise HTTPException(503,'Email actions are disabled in this preview',headers={'Cache-Control':'no-store'})


def accepted(response):
    response.headers['Cache-Control']='no-store'
    return {'status':'accepted'}


def deliver(purpose,*,email=None,owner_id=None,session_id=None):
    """After-response best-effort local delivery; unknown addresses follow the same API path."""
    if not local_enabled():return
    published=None;action_id=None
    try:
        with SessionLocal.begin() as db:
            user=db.get(User,owner_id) if owner_id else db.scalar(select(User).where(User.email==email,User.deleted_at.is_(None)))
            if user is None or user.deleted_at is not None:return
            lock_owner(db,user.id);db.refresh(user)
            if session_id and not db.scalar(select(AuthSession.id).where(AuthSession.id==session_id,
                AuthSession.user_id==user.id,AuthSession.revoked_at.is_(None),AuthSession.expires_at>utcnow())):return
            if purpose=='verify' and user.email_verified_at is not None:return
            raw=secrets.token_urlsafe(32);now=utcnow()
            action=AuthAction(user_id=user.id,purpose=purpose,token_hash=token_hash(raw),account_digest=account_digest(user),
                created_at=now,expires_at=now+timedelta(minutes=get_settings().auth_action_minutes))
            db.add(action);db.flush();action_id=action.id;recipient=user.email
        # Publish only after commit: a reader of the atomic local message must
        # never race an uncommitted action record. Delivery is still best effort.
        published=write_local_message(action,recipient,raw)
    except Exception:
        if action_id:
            try:
                with SessionLocal.begin() as db:
                    db.execute(update(AuthAction).where(AuthAction.id==action_id,AuthAction.used_at.is_(None)).values(used_at=utcnow()))
            except SQLAlchemyError:pass
        if published:
            try:published.unlink(missing_ok=True)
            except OSError:pass
        # No email, token, exception text, path or provider payload in logs.
        logger.warning('local authentication message delivery deferred')


class EmailRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email:EmailStr


class CodeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    code:str=Field(min_length=43,max_length=43,pattern=r'^[A-Za-z0-9_-]{43}$')


class ResetRequest(CodeRequest):
    new_password:str=Field(min_length=12,max_length=128)


@router.get('/recovery-capabilities')
def capabilities(response:Response):
    response.headers['Cache-Control']='no-store'
    return {'delivery':'local_file' if local_enabled() else 'disabled','verification_enforced':False}


@router.post('/password-reset/request',status_code=202)
def request_reset(payload:EmailRequest,request:Request,response:Response,tasks:BackgroundTasks):
    settings=get_settings();email=str(payload.email).strip().lower()
    consume_limits([('reset-request-ip',peer(request),settings.auth_login_ip_limit),
                    ('reset-request-email',email,settings.auth_action_email_limit)])
    if local_enabled():tasks.add_task(deliver,'reset',email=email)
    return accepted(response)


@router.post('/email-verification/request',status_code=202)
def request_verification(request:Request,response:Response,tasks:BackgroundTasks,auth:AuthContext=Depends(current_auth)):
    settings=get_settings()
    consume_limits([('verify-request-ip',peer(request),settings.auth_login_ip_limit),
                    ('verify-request-email',auth.user.email,settings.auth_action_email_limit)])
    if local_enabled():tasks.add_task(deliver,'verify',owner_id=auth.user.id,session_id=auth.session.id)
    return accepted(response)


def action_owner(db,code,purpose):
    action=db.scalar(select(AuthAction).where(AuthAction.token_hash==token_hash(code),AuthAction.purpose==purpose))
    if action is None:raise HTTPException(400,INVALID,headers={'Cache-Control':'no-store'})
    try:lock_owner(db,action.user_id)
    except HTTPException:raise HTTPException(400,INVALID,headers={'Cache-Control':'no-store'}) from None
    db.refresh(action);user=db.get(User,action.user_id);db.refresh(user)
    expiry=action.expires_at if action.expires_at.tzinfo else action.expires_at.replace(tzinfo=timezone.utc)
    if action.used_at is not None or expiry<=utcnow() or not hmac.compare_digest(action.account_digest,account_digest(user)):
        raise HTTPException(400,INVALID,headers={'Cache-Control':'no-store'})
    return action,user


def limit_confirmation(request,code,purpose):
    consume_limits([(purpose+'-confirm-ip',peer(request),get_settings().auth_login_ip_limit),
                    (purpose+'-confirm-code',token_hash(code),get_settings().auth_password_limit)])


@router.post('/password-reset/confirm',status_code=204)
def confirm_reset(payload:ResetRequest,request:Request,db:Session=Depends(session_dep)):
    require_enabled();limit_confirmation(request,payload.code,'reset')
    new_hash=make_password_hash(payload.new_password)
    _,user=action_owner(db,payload.code,'reset')
    user.password_hash=new_hash;invalidate_actions(db,user.id)
    revoke_families(db,user.id)
    db.execute(update(AuthSession).where(AuthSession.user_id==user.id,AuthSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    db.commit()
    return Response(status_code=204,headers={'Cache-Control':'no-store'})


@router.post('/email-verification/confirm',status_code=204)
def confirm_verification(payload:CodeRequest,request:Request,db:Session=Depends(session_dep)):
    require_enabled();limit_confirmation(request,payload.code,'verify')
    _,user=action_owner(db,payload.code,'verify')
    user.email_verified_at=utcnow();user.email_verification_method='local_file'
    invalidate_actions(db,user.id,'verify');db.commit()
    return Response(status_code=204,headers={'Cache-Control':'no-store'})
