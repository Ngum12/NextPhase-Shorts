"""Encrypted auth delivery, owner-first locks, fenced leases and shared attempt caps."""
from datetime import timedelta,timezone
import hmac
import json
import secrets
import uuid
from cryptography.fernet import Fernet,MultiFernet,InvalidToken
from sqlalchemy import select,update,or_,func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from .auth_action_tokens import account_digest,token_hash
from .config import get_settings
from .db import SessionLocal,engine
from .models import AuthAction,AuthSession,MailOutbox,MailBudget,User,utcnow
from .queue import lock_owner
from . import mail_transport

ACTIVE=('pending','retry','sending')


def aware(value):return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def real_enabled():
    settings=get_settings()
    return settings.auth_mail_backend=='resend' and settings.auth_mail_send_enabled


def cipher():
    return MultiFernet([Fernet(key.encode()) for key in get_settings().auth_mail_keys])


def enqueue(purpose,*,email=None,owner_id=None,session_id=None):
    if not real_enabled():return
    with SessionLocal.begin() as db:
        user=db.get(User,owner_id) if owner_id else db.scalar(select(User).where(User.email==email,User.deleted_at.is_(None)))
        if user is None or user.deleted_at is not None:return
        lock_owner(db,user.id);db.refresh(user)
        if session_id and not db.scalar(select(AuthSession.id).where(AuthSession.id==session_id,
                AuthSession.user_id==user.id,AuthSession.revoked_at.is_(None),AuthSession.expires_at>utcnow())):return
        if purpose=='verify' and user.email_verified_at and user.email_verification_method=='resend':return
        now=utcnow()
        pending=db.scalar(select(func.count()).select_from(MailOutbox).where(MailOutbox.user_id==user.id,
            MailOutbox.state.in_(ACTIVE),MailOutbox.expires_at>now))
        if pending>=3:return  # Durable per-owner admission, in addition to request windows.
        raw=secrets.token_urlsafe(32)
        action=AuthAction(id=str(uuid.uuid4()),user_id=user.id,purpose=purpose,token_hash=token_hash(raw),
            account_digest=account_digest(user),created_at=now,
            expires_at=now+timedelta(minutes=get_settings().auth_action_minutes),delivery_method='resend')
        row=MailOutbox(id=str(uuid.uuid4()),user_id=user.id,action_id=action.id,created_at=now,
            expires_at=action.expires_at,due_at=now)
        subject='Confirm your NextPhase Shorts email' if purpose=='verify' else 'Reset your NextPhase Shorts password'
        message={'from':'NextPhase Shorts <'+get_settings().auth_mail_from+'>','to':[user.email],
            'subject':subject,'text':subject+'\n\nEnter this code in NextPhase Shorts:\n'+raw+
            '\n\nExpires at '+action.expires_at.isoformat()+'. Use it once. Never share it.\n'
            'If you did not request this, ignore this message. Your password has not changed.'}
        envelope={'id':row.id,'action':action.id,'owner':user.id,'code':raw,'message':message}
        row.payload=cipher().encrypt(json.dumps(envelope,separators=(',',':')).encode()).decode()
        db.add(action);db.flush();db.add(row)
        # Action and encrypted delivery intent commit together; no background task gap.


def terminal(db,row,state,code):
    row.state=state;row.last_code=code;row.payload=None;row.lease_token=None;row.lease_until=None
    if state!='accepted':
        db.execute(update(AuthAction).where(AuthAction.id==row.action_id,AuthAction.used_at.is_(None)).values(used_at=utcnow()))


def reserve_budget(db,now):
    insert=pg_insert if engine.dialect.name=='postgresql' else sqlite_insert
    db.execute(insert(MailBudget).values(id='resend',day='',month='',daily_attempts=0,monthly_attempts=0,next_send_at=now)
        .on_conflict_do_nothing(index_elements=['id']))
    row=db.scalar(select(MailBudget).where(MailBudget.id=='resend').with_for_update())
    day=now.strftime('%Y-%m-%d');month=now.strftime('%Y-%m')
    if row.day>day or row.month>month:return 'local_clock_skew',now+timedelta(minutes=1)
    if row.day!=day:row.day=day;row.daily_attempts=0
    if row.month!=month:row.month=month;row.monthly_attempts=0
    settings=get_settings()
    if row.daily_attempts>=settings.auth_mail_daily_limit or row.monthly_attempts>=settings.auth_mail_monthly_limit:
        return 'local_quota',now+timedelta(minutes=5)
    if aware(row.next_send_at)>now:return 'local_throttle',aware(row.next_send_at)
    row.daily_attempts+=1;row.monthly_attempts+=1;row.next_send_at=now+timedelta(seconds=1)
    return None,None


def claim():
    if not real_enabled():return None
    now=utcnow()
    eligible=(MailOutbox.due_at<=now,MailOutbox.state.in_(ACTIVE),
        or_(MailOutbox.state!='sending',MailOutbox.lease_until<=now))
    with SessionLocal() as db:
        candidate=db.execute(select(MailOutbox.id,MailOutbox.user_id).where(*eligible)
            .order_by(MailOutbox.due_at,MailOutbox.id).limit(1)).first()
    if not candidate:return None
    with SessionLocal.begin() as db:
        # Same order as reset/deletion: owner then outbox, never outbox then owner.
        lock_owner(db,candidate.user_id,allow_deleted=True)
        row=db.scalar(select(MailOutbox).where(MailOutbox.id==candidate.id,*eligible))
        if row is None:return None
        action=db.get(AuthAction,row.action_id);user=db.get(User,row.user_id)
        if (aware(row.expires_at)<=now or action is None or action.used_at or user.deleted_at
                or action.delivery_method!='resend' or not hmac.compare_digest(action.account_digest,account_digest(user))):
            terminal(db,row,'cancelled','stale_action');return None
        if row.attempts>=5:
            terminal(db,row,'failed','attempts_exhausted');return None
        try:
            envelope=json.loads(cipher().decrypt(row.payload.encode()))
            if (envelope['id']!=row.id or envelope['action']!=action.id or envelope['owner']!=user.id
                    or envelope['message']['to']!=[user.email] or token_hash(envelope['code'])!=action.token_hash):
                raise ValueError('binding')
        except (InvalidToken,ValueError,TypeError,KeyError,AttributeError):
            terminal(db,row,'failed','payload_unavailable');return None
        recipients=get_settings().auth_mail_recipients
        if ((get_settings().env in ('development','test') or recipients) and user.email not in recipients):
            terminal(db,row,'failed','recipient_not_allowed');return None
        code,due=reserve_budget(db,now)
        if code:
            row.state='retry';row.last_code=code;row.due_at=due;row.lease_token=None;row.lease_until=None
            return None
        token=str(uuid.uuid4());row.state='sending';row.lease_token=token
        row.lease_until=now+timedelta(seconds=90);row.attempts+=1
        return {'id':row.id,'owner':row.user_id,'token':token,'message':envelope['message'],'attempt':row.attempts}


def dispatch_one():
    work=claim()
    if work is None:return False
    failure=None
    try:mail_transport.send(work['message'],work['id'])
    except mail_transport.MailFailure as error:failure=error
    except Exception:failure=mail_transport.MailFailure('transport_internal',retry=True)
    with SessionLocal.begin() as db:
        lock_owner(db,work['owner'],allow_deleted=True)
        row=db.scalar(select(MailOutbox).where(MailOutbox.id==work['id'],MailOutbox.state=='sending',MailOutbox.lease_token==work['token']))
        if row is None:return True  # Reset/deletion or another claimant won; don't overwrite.
        if aware(row.lease_until)<=utcnow():return True  # Stale sender cannot publish completion.
        if failure is None:terminal(db,row,'accepted','provider_accepted')
        elif failure.retry and row.attempts<5 and aware(row.expires_at)>utcnow():
            row.state='retry';row.last_code=failure.code;row.lease_token=None;row.lease_until=None
            row.due_at=utcnow()+timedelta(seconds=max(failure.delay,min(300,2**row.attempts*5)))
        else:terminal(db,row,'failed',failure.code)
    return True


def cleanup_mail(limit=1000):
    if not 1<=limit<=1000:raise ValueError('Mail cleanup batch must be 1–1000')
    now=utcnow()
    with SessionLocal() as db:
        rows=list(db.execute(select(MailOutbox.id,MailOutbox.user_id).where(MailOutbox.expires_at<=now)
            .order_by(MailOutbox.expires_at,MailOutbox.id).limit(limit)))
    for identity,owner in rows:
        with SessionLocal.begin() as db:
            lock_owner(db,owner,allow_deleted=True)
            row=db.get(MailOutbox,identity)
            if row and aware(row.expires_at)<=now:
                if row.state in ACTIVE:terminal(db,row,'cancelled','expired')
                # Keep no recipient/proof ciphertext after expiry, even if state was corrupt.
                row.payload=None
                if aware(row.expires_at)<now-timedelta(days=1):db.delete(row)
    return len(rows)


def reencrypt_pending(after=''):
    """Offline bounded rotation; do not print/decrypt payloads to an operator."""
    with SessionLocal() as db:
        rows=list(db.execute(select(MailOutbox.id,MailOutbox.user_id).where(MailOutbox.payload.is_not(None),MailOutbox.id>after)
            .order_by(MailOutbox.id).limit(1000)))
    for identity,owner in rows:
        with SessionLocal.begin() as db:
            lock_owner(db,owner,allow_deleted=True);row=db.get(MailOutbox,identity)
            if row and row.payload:
                try:row.payload=cipher().rotate(row.payload.encode()).decode()
                except InvalidToken:terminal(db,row,'failed','payload_unavailable')
    return {'processed':len(rows),'next_after':rows[-1][0] if len(rows)==1000 else None}
