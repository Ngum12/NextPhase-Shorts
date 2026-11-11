"""Disable access atomically; remove owner media later with durable retry/resweeps."""
from datetime import timedelta,timezone
import hashlib
import json
import logging
import shutil
import uuid
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from pydantic import BaseModel,Field,UUID4
from sqlalchemy import select,update,delete,func,case
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .auth import AuthContext,current_auth,verify_password,unauthorized
from .auth_routes import peer
from .auth_limits import consume_limits
from .auth_action_tokens import invalidate_actions
from .config import get_settings
from .db import SessionLocal,engine,session_dep
from .models import User,AuthSession,AccountDeletion,RenderJob,RenderAttempt,UploadSession,UploadPart,DirectUploadGrant,utcnow
from .models import ProjectAnalysis
from .queue import lock_owner
from .refresh import revoke_families
from . import object_store as store

router=APIRouter(prefix='/api/v1/account',tags=['account deletion'])
logger=logging.getLogger('nextphase.account-deletion')


def aware(value):return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
def receipt_hash(key):return hashlib.sha256(str(key).encode()).hexdigest()


class DeleteRequest(BaseModel):
    current_password:str=Field(min_length=1,max_length=128)
    receipt_key:UUID4


class ReceiptRequest(BaseModel):
    receipt_key:UUID4


def result(row):
    return {'status':'account_disabled','media_cleanup':'verified' if row.media_cleaned_at else 'scheduled'}


@router.post('/delete',status_code=202)
def delete_account(payload:DeleteRequest,request:Request,response:Response,
                   auth:AuthContext=Depends(current_auth),db:Session=Depends(session_dep)):
    settings=get_settings()
    consume_limits([('delete-account-ip',peer(request),settings.auth_login_ip_limit),
                    ('delete-account-owner',auth.user.id,settings.auth_password_limit)])
    lock_owner(db,auth.user.id);db.refresh(auth.user)
    active=db.scalar(select(AuthSession.id).where(AuthSession.id==auth.session.id,
        AuthSession.revoked_at.is_(None),AuthSession.expires_at>utcnow()))
    if active is None:raise unauthorized()
    if not verify_password(payload.current_password,auth.user.password_hash):
        db.rollback();raise HTTPException(400,'Current password is incorrect')
    from .restore_journal import record
    now=utcnow();uid=auth.user.id
    if db.scalar(select(AccountDeletion.user_id).where(AccountDeletion.receipt_hash==receipt_hash(payload.receipt_key))):
        raise HTTPException(409,'Deletion confirmation key is unavailable. Start a new request.')
    after=now+timedelta(seconds=settings.upload_part_timeout_seconds+90)
    lease=db.scalar(select(func.max(RenderJob.lease_expires_at)).where(RenderJob.user_id==uid))
    hard=db.scalar(select(func.max(RenderJob.claim_deadline_at)).where(RenderJob.user_id==uid))
    attempts=db.scalar(select(func.max(RenderAttempt.deadline_at)).join(RenderJob,RenderAttempt.job_id==RenderJob.id)
        .where(RenderJob.user_id==uid,RenderAttempt.status.in_(('running','lease_lost','cancelled'))))
    grants=db.scalar(select(func.max(DirectUploadGrant.expires_at)).join(UploadSession,
        UploadSession.id==DirectUploadGrant.session_id).where(UploadSession.user_id==uid))
    for deadline in (lease,hard,attempts,grants):
        if deadline:after=max(after,aware(deadline)+timedelta(seconds=30))
    namespaces=set(db.scalars(select(RenderJob.object_store_id).where(RenderJob.user_id==uid,RenderJob.media_backend=='s3')))
    namespaces.update(db.scalars(select(UploadSession.object_store_id).where(UploadSession.user_id==uid,UploadSession.transfer_backend=='direct-s3')))
    if settings.media_backend=='s3':namespaces.add(store.namespace_id())
    # Keep an unknown marker; do not claim old remote media was erased by guessing.
    namespaces={value or 'unknown' for value in namespaces}
    record('account_delete',uid,namespace=sorted(namespaces))
    db.execute(delete(ProjectAnalysis).where(ProjectAnalysis.job_id.in_(
        select(RenderJob.id).where(RenderJob.user_id==uid))))
    row=AccountDeletion(user_id=uid,receipt_hash=receipt_hash(payload.receipt_key),
        receipt_expires_at=now+timedelta(days=7),requested_at=now,cleanup_after=after,
        namespaces=json.dumps(sorted(namespaces)))
    db.add(row)
    auth.user.deleted_at=now;auth.user.email='!deleted:'+uid;auth.user.password_hash='!disabled'
    auth.user.email_verified_at=None;auth.user.email_verification_method=None
    invalidate_actions(db,uid)
    revoke_families(db,uid)
    db.execute(update(AuthSession).where(AuthSession.user_id==uid,AuthSession.revoked_at.is_(None)).values(revoked_at=now))
    # Revoke all claims in the same owner transaction, before any media I/O.
    db.execute(update(RenderJob).where(RenderJob.user_id==uid).values(status='deleted',deleted_at=now,
        cleanup_after=after,finished_at=now,claim_token=None,lease_expires_at=None,error_code=None,
        title='Deleted project',source_path='',output_path=None,output_duration_seconds=None,media_deleted_at=None,
        preview_spec_json=None))
    db.execute(update(RenderAttempt).where(RenderAttempt.job_id.in_(select(RenderJob.id).where(RenderJob.user_id==uid)),
        RenderAttempt.status=='running').values(status='cancelled',finished_at=now))
    db.execute(update(UploadSession).where(UploadSession.user_id==uid).values(
        status=case((UploadSession.job_id.is_(None),'aborted'),else_='deleted'),title='Deleted upload',
        file_name='deleted.mp4',source_sha256=None,parts_cleaned=False))
    try:db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'Deletion confirmation key is unavailable. Start a new request.')
    response.headers['Cache-Control']='private, no-store'
    return result(row)


@router.post('/deletion-receipt')
def deletion_receipt(payload:ReceiptRequest,request:Request,response:Response,db:Session=Depends(session_dep)):
    # An opaque random capability recovers a lost deletion response after all
    # authentication sessions have been revoked. It reveals no account identity.
    consume_limits([('deletion-receipt-ip',peer(request),get_settings().auth_login_ip_limit)])
    row=db.scalar(select(AccountDeletion).where(AccountDeletion.receipt_hash==receipt_hash(payload.receipt_key),
                                              AccountDeletion.receipt_expires_at>utcnow()))
    if row is None:raise HTTPException(404,'Deletion confirmation is unavailable')
    response.headers['Cache-Control']='private, no-store'
    return result(row)


def remove_owner_tree(uid):
    if str(uuid.UUID(uid))!=uid:raise ValueError('Noncanonical owner identity')
    target=get_settings().storage_dir/uid
    if target.is_symlink() or getattr(target,'is_junction',lambda:False)():
        raise ValueError('Unsafe owner tree')
    try:shutil.rmtree(target)
    except FileNotFoundError:pass


def cleanup_accounts(limit=5):
    if not 1<=limit<=100:raise ValueError('Account cleanup limit must be 1–100')
    with SessionLocal() as db:
        rows=list(db.execute(select(AccountDeletion.user_id,AccountDeletion.namespaces).where(
            AccountDeletion.cleanup_after<=utcnow()).order_by(
            case((AccountDeletion.media_cleaned_at.is_(None),0),else_=1),
            func.coalesce(AccountDeletion.attempted_at,AccountDeletion.requested_at)).limit(limit)))
    cleaned=0
    for uid,namespaces in rows:
        success=False
        try:
            with SessionLocal() as db:
                user=db.get(User,uid)
                if user is None or user.deleted_at is None:raise RuntimeError('Account not disabled')
            required=json.loads(namespaces)
            if required:
                if any(value!=store.namespace_id() for value in required):raise RuntimeError('Storage namespace mismatch')
                store.remove_owner(uid)
            remove_owner_tree(uid)
            success=True
        except (OSError,ValueError,RuntimeError):logger.warning('account media cleanup deferred')
        with SessionLocal.begin() as db:
            db.execute(update(AccountDeletion).where(AccountDeletion.user_id==uid).values(
                attempted_at=utcnow(),media_cleaned_at=utcnow() if success else None))
            if success:
                db.execute(update(RenderJob).where(RenderJob.user_id==uid,RenderJob.status=='deleted').values(media_deleted_at=utcnow()))
                ids=select(UploadSession.id).where(UploadSession.user_id==uid)
                db.execute(delete(UploadPart).where(UploadPart.session_id.in_(ids)))
                db.execute(update(UploadSession).where(UploadSession.user_id==uid).values(parts_cleaned=True))
        cleaned+=int(success)
    return cleaned


if __name__=='__main__':
    from .migrate import require_current_schema
    require_current_schema(engine)
    print(f'Verified {cleanup_accounts()} disabled-account media cleanups.')
