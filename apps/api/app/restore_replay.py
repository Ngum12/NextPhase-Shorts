"""Offline restore gate. Revoke every old credential and reapply journal tombstones.

Only run against an isolated restored target with API/workers/mail/ingress stopped.
No filesystem/S3 deletion or provider calls occur here; existing cleanup owns I/O.
"""
import argparse
from datetime import datetime,timedelta
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import select,update,case
from .restore_journal import JournalError,canonical,configured,identity,MAX_RECORDS
from .models import (User,AuthSession,RefreshFamily,AuthAction,MailOutbox,RenderJob,
                     RenderAttempt,UploadSession,AccountDeletion,QueueSignal,RestoreJournalBinding,utcnow)


def require_binding(engine,journal):
    from sqlalchemy.orm import Session
    with Session(engine) as db:binding=db.get(RestoreJournalBinding,1)
    if journal is None:
        if binding is not None:raise JournalError()
        return
    checkpoint=journal.ready()
    if binding is None or binding.journal_id!=checkpoint['journal_id']:raise JournalError()


def bind(journal,engine,*,offline=False):
    """One-time opt-in on the current stopped source, never on an old restore."""
    from sqlalchemy.orm import Session
    from .migrate import require_current_schema
    if not offline:raise JournalError()
    require_current_schema(engine)
    checkpoint=journal.ready()
    with Session(engine) as db:
        existing=db.get(RestoreJournalBinding,1)
        if existing:
            if existing.journal_id!=checkpoint['journal_id']:raise JournalError()
            return {'binding':'already protected'}
        # Bootstrap current tombstones before accepting any future protected
        # snapshot. Never backfill missing deletion history from an old dump.
        accounts=list(db.scalars(select(AccountDeletion).limit(50001)))
        projects=list(db.scalars(select(RenderJob).where(RenderJob.status=='deleted').limit(50001)))
        if len(accounts)+len(projects)>50000:raise JournalError()
        for row in accounts:
            journal.append({'kind':'account_delete','owner':row.user_id,'project':None,'backend':None,'namespace':json.loads(row.namespaces)})
        for job in projects:
            journal.append({'kind':'project_delete','owner':job.user_id,'project':job.id,'backend':job.media_backend,
                            'namespace':(job.object_store_id or 'unknown') if job.media_backend=='s3' else job.object_store_id})
        # Offline source only; no concurrent writer can replace the stream here.
        if journal.ready()['journal_id']!=checkpoint['journal_id']:raise JournalError()
        db.add(RestoreJournalBinding(id=1,journal_id=checkpoint['journal_id'],bound_at=utcnow()));db.commit()
    return {'binding':'protected','existing_account_tombstones':len(accounts),'existing_project_tombstones':len(projects)}


def expected_checkpoint(path):
    try:
        value=json.loads(Path(path).read_bytes())
        if set(value)!={'schema_version','journal_id','count','head'}:raise JournalError()
        if type(value['schema_version']) is not int or value['schema_version']!=1 or not identity(value['journal_id']):raise JournalError()
        if type(value['count']) is not int or not 0<=value['count']<MAX_RECORDS or not isinstance(value['head'],str) or len(value['head'])!=64 or any(c not in '0123456789abcdef' for c in value['head']):raise JournalError()
        return value
    except (OSError,ValueError,TypeError):raise JournalError() from None


def hold(journal,value):
    path=journal.root/'restore-hold.json'
    if path.exists():journal.safe(path)
    temporary=journal.root/'restore-hold.tmp'
    descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(descriptor,'wb') as handle:
            handle.write(canonical(value));handle.flush();os.fsync(handle.fileno())
        os.replace(temporary,path);journal.sync_directory()
    finally:temporary.unlink(missing_ok=True)


def tombstone_job(db,job,now,after):
    job.status='deleted';job.deleted_at=now;job.finished_at=now;job.cleanup_after=after
    job.claim_token=None;job.lease_expires_at=None;job.claim_deadline_at=None
    job.title='Deleted project';job.source_path='';job.output_path=None
    job.error_code=None;job.output_duration_seconds=None;job.media_deleted_at=None
    db.execute(update(RenderAttempt).where(RenderAttempt.job_id==job.id,RenderAttempt.status=='running')
        .values(status='cancelled',finished_at=now))
    db.execute(update(UploadSession).where(UploadSession.job_id==job.id)
        .values(status='deleted',title='Deleted project',file_name='deleted.mp4',source_sha256=None,parts_cleaned=False))


def apply_records(db,records):
    from .config import get_settings
    settings=get_settings();now=utcnow()
    # Stop/retire old remote capabilities and writers before applying. Waiting this
    # conservative maximum also protects cleanup from a pre-restore late write.
    after=now+timedelta(seconds=settings.render_timeout_seconds+settings.upload_part_timeout_seconds+120)
    db.execute(update(AuthSession).where(AuthSession.revoked_at.is_(None)).values(revoked_at=now))
    db.execute(update(RefreshFamily).where(RefreshFamily.revoked_at.is_(None)).values(revoked_at=now))
    db.execute(update(AuthAction).where(AuthAction.used_at.is_(None)).values(used_at=now))
    db.execute(update(MailOutbox).where(MailOutbox.state.in_(('pending','retry','sending'))).values(state='cancelled',payload=None,lease_token=None,lease_until=None,last_code='restore_revoked'))
    # Never restore a former password or process an old email proof. Recover through
    # a newly issued, approved real email channel after cutover. No bypass endpoint.
    db.execute(update(User).where(User.deleted_at.is_(None)).values(password_hash='!restore-recovery-required'))
    db.execute(update(RenderJob).where(RenderJob.status.in_(('queued','processing')))
        .values(status='cancelled',claim_token=None,lease_expires_at=None,claim_deadline_at=None,finished_at=now))
    db.execute(update(RenderAttempt).where(RenderAttempt.status=='running').values(status='cancelled',finished_at=now))
    db.execute(update(QueueSignal).values(completed_at=now,lease_token=None,lease_until=None))
    db.execute(update(UploadSession).where(UploadSession.status=='uploading').values(status='aborted',parts_cleaned=False))
    account_namespaces={}
    projects={}
    for row in records:
        if row['kind']=='account_delete':account_namespaces.setdefault(row['owner'],set()).update(row['namespace'])
        elif row['kind']=='project_delete':
            identity=(row['owner'],row['project'])
            if identity in projects and projects[identity]!=row:raise JournalError()
            projects[identity]=row
    owners=set(account_namespaces)|{owner for owner,_ in projects}
    for uid in sorted(owners):
        user=db.get(User,uid)
        if user is None:
            user=User(id=uid,email='!restored-tombstone:'+uid,password_hash='!disabled',created_at=now,deleted_at=now)
            db.add(user);db.flush()
        if uid in account_namespaces:
            required=account_namespaces[uid]
            required.update(value or 'unknown' for value in db.scalars(select(RenderJob.object_store_id).where(RenderJob.user_id==uid,RenderJob.media_backend=='s3')))
            required.update(value or 'unknown' for value in db.scalars(select(UploadSession.object_store_id).where(UploadSession.user_id==uid,UploadSession.transfer_backend=='direct-s3')))
            existing=db.get(AccountDeletion,uid)
            if existing:required.update(json.loads(existing.namespaces))
            user.deleted_at=now;user.email='!deleted:'+uid;user.password_hash='!disabled'
            user.email_verified_at=None;user.email_verification_method=None
            if existing is None:
                existing=AccountDeletion(user_id=uid,receipt_hash=hashlib.sha256(('restore-deleted:'+uid).encode()).hexdigest(),
                    receipt_expires_at=now,requested_at=now,cleanup_after=after,namespaces='[]')
                db.add(existing)
            existing.cleanup_after=after;existing.media_cleaned_at=None;existing.namespaces=json.dumps(sorted(required))
            for job in db.scalars(select(RenderJob).where(RenderJob.user_id==uid)):tombstone_job(db,job,now,after)
            db.execute(update(UploadSession).where(UploadSession.user_id==uid).values(
                status=case((UploadSession.job_id.is_(None),'aborted'),else_='deleted'),title='Deleted upload',
                file_name='deleted.mp4',source_sha256=None,parts_cleaned=False))
    for (uid,jid),row in sorted(projects.items()):
        job=db.get(RenderJob,jid)
        if job is not None and job.user_id!=uid:raise JournalError()
        if job is None:
            # A post-snapshot project can still exist in current remote storage.
            # Preserve its canonical cleanup identity even if absent in the DB dump.
            job=RenderJob(id=jid,user_id=uid,title='Deleted project',style='vlog',desired_seconds=5,
                source_duration_seconds=0,source_path='',media_backend=row['backend'],object_store_id=row['namespace'],
                storage_reserved_bytes=0,max_render_bytes=settings.max_render_bytes,status='deleted')
            db.add(job);db.flush()
        elif job.media_backend!=row['backend'] or job.object_store_id!=row['namespace']:
            raise JournalError()
        tombstone_job(db,job,now,after)
    db.flush()
    return {'account_tombstones':len(account_namespaces),'project_tombstones':len(projects),
            'all_credentials':'revoked; password recovery required','active_work':'cancelled',
            'media_cleanup':'scheduled; not erased by replay'}


def replay(journal,engine,checkpoint,*,apply=False,offline=False):
    from sqlalchemy.orm import Session
    from .migrate import require_current_schema
    if apply and not offline:raise JournalError()
    with journal.locked():
        actual,records=journal._read()
        if actual!=checkpoint:raise JournalError()
        require_current_schema(engine)
        with Session(engine) as db:
            binding=db.get(RestoreJournalBinding,1)
            if binding is None or binding.journal_id!=actual['journal_id']:raise JournalError()
        if not apply:return {**actual,'events':len(records),'mode':'preview','target_modified':False}
        release_after=(utcnow()+timedelta(seconds=120)).isoformat()
        hold(journal,{'checkpoint':actual,'applied':False,'release_after':release_after})
        with Session(engine) as db:
            with db.begin():result=apply_records(db,records)
        hold(journal,{'checkpoint':actual,'applied':True,'release_after':release_after})
        return {**actual,**result,'mode':'applied','access':'held until explicit offline release'}


def release(journal,checkpoint,*,offline=False,now=None):
    if not offline:raise JournalError()
    with journal.locked():
        if journal._read()[0]!=checkpoint:raise JournalError()
        path=journal.root/'restore-hold.json';journal.safe(path)
        state=json.loads(path.read_bytes())
        if set(state)!={'checkpoint','applied','release_after'} or state['checkpoint']!=checkpoint or state['applied'] is not True:raise JournalError()
        deadline=datetime.fromisoformat(state['release_after'])
        if deadline.tzinfo is None or (now or utcnow())<deadline:raise JournalError()
        path.unlink();journal.sync_directory()
    return {'access':'released; verify cleanup and recovery before cutover'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--init',action='store_true');actions.add_argument('--checkpoint',action='store_true')
    actions.add_argument('--bind',action='store_true');actions.add_argument('--replay',action='store_true');actions.add_argument('--release',action='store_true')
    parser.add_argument('--expected-checkpoint',type=Path)
    parser.add_argument('--apply',action='store_true');parser.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    try:
        journal=configured()
        if journal is None:raise JournalError()
        if args.init:result=journal.initialize()
        elif args.checkpoint:result=journal.checkpoint()
        elif args.bind:
            from .db import engine
            result=bind(journal,engine,offline=args.offline)
        else:
            if not args.expected_checkpoint:raise JournalError()
            checkpoint=expected_checkpoint(args.expected_checkpoint)
            if args.release:result=release(journal,checkpoint,offline=args.offline)
            else:
                from .db import engine
                result=replay(journal,engine,checkpoint,apply=args.apply,offline=args.offline)
        print(json.dumps(result,sort_keys=True))
    except Exception:
        parser.exit(1,'Restore journal operation refused; verify private configuration, current checkpoint and offline state.\n')


if __name__=='__main__':main()
