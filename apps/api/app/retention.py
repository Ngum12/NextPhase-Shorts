"""Preview-first, offline orphan/stale-attempt inventory. Never expire valid projects."""
import argparse
from collections import Counter
from datetime import timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import uuid
from sqlalchemy import select, or_
from .config import get_settings
from .db import SessionLocal, engine
from .models import RenderAttempt, RenderJob, UploadSession, UploadPart, User, utcnow
from . import object_store as store
from botocore.exceptions import BotoCoreError, ClientError


class RetentionError(RuntimeError):
    pass


def canonical(value):
    try: return str(uuid.UUID(value)) == value
    except (ValueError, TypeError, AttributeError): return False


def aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def referenced(db, identity):
    pattern='%'+identity+'%'
    return bool(db.scalar(select(RenderJob.id).where(or_(RenderJob.source_path.like(pattern),
        RenderJob.output_path.like(pattern))).limit(1)) or
        db.scalar(select(UploadPart.session_id).where(UploadPart.object_reference.like(pattern)).limit(1)))


def eligible(db, owner, entity, kind, token=None, backend='local'):
    if not canonical(owner) or not canonical(entity) or db.get(User, owner) is None:
        return False
    job, session = db.get(RenderJob, entity), db.get(UploadSession, entity)
    if kind in ('orphan-media', 'orphan-upload'):
        # Global identities protect even misplaced/cross-owner known resources.
        return job is None and session is None and not referenced(db,entity)
    if kind != 'stale-attempt' or not canonical(token) or job is None or job.user_id != owner:
        return False
    if job.status not in ('succeeded', 'failed', 'cancelled') or job.claim_token == token:
        return False
    if backend=='s3' and (job.media_backend!='s3' or job.object_store_id!=store.namespace_id()):
        return False
    if any('/'+token+'/' in (value or '').replace('\\','/') for value in (job.source_path, job.output_path)):
        return False
    if referenced(db,token):
        return False
    attempt = db.get(RenderAttempt, token)
    return bool(attempt and attempt.job_id == entity and attempt.status in ('failed','cancelled','lease_lost'))


def allowed_file(relative, kind):
    parts = relative.split('/')
    if kind == 'orphan-upload':
        return len(parts)==1 and bool(re.fullmatch(r'(?:0|[1-9][0-9]*)-[a-f0-9]{64}\.part',parts[0]) or
            (parts[0].endswith('.staging') and canonical(parts[0][:-8])))
    if kind == 'stale-attempt':
        return len(parts)==1 and parts[0] in ('output.mp4','input.media')
    return ((len(parts)==1 and parts[0] in ('input.mp4','input.mov','input.webm','input.m4v')) or
            (len(parts)==2 and canonical(parts[0]) and parts[1] in ('output.mp4','input.media')))


class Inventory:
    def __init__(self, backend, grace_hours, scan_limit, now):
        if backend not in ('local','s3') or not 24<=grace_hours<=8760 or not 1<=scan_limit<=50000:
            raise RetentionError('Use local/s3, a 24–8760 hour grace and scan limit 1–50000')
        self.backend=backend;self.grace_hours=grace_hours;self.scan_limit=scan_limit
        self.now=now;self.cutoff=now-timedelta(hours=grace_hours)
        self.scanned=0;self.truncated=False;self.counts=Counter();self.candidates=[]

    def tick(self):
        self.scanned+=1
        if self.scanned>self.scan_limit:
            self.truncated=True;raise RetentionError('scan limit')

    def tree(self, target, kind):
        """Bounded depth, no symlinks/junctions/hardlinks/special/unknown files."""
        records=[]
        def visit(path, relative='', depth=0):
            self.tick();info=path.lstat()
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise ValueError('link')
            if max(info.st_mtime, info.st_ctime)>self.cutoff.timestamp():raise ValueError('young')
            directory=stat.S_ISDIR(info.st_mode)
            if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or not allowed_file(relative,kind)):
                raise ValueError('unknown file')
            if directory and relative and (kind!='orphan-media' or depth!=1 or not canonical(path.name)):
                raise ValueError('unknown directory')
            records.append([relative,info.st_dev,info.st_ino,info.st_mode,info.st_size,info.st_mtime_ns,info.st_ctime_ns])
            if directory:
                with os.scandir(path) as children:
                    for child in children:visit(Path(child.path), (relative+'/' if relative else '')+child.name,depth+1)
        visit(target)
        return sorted(records)

    def local(self, db):
        root=get_settings().storage_dir
        def entries(path):
            with os.scandir(path) as items:
                for item in items:
                    self.tick();yield Path(item.path)
        def safe_dir(path):
            return path.is_dir() and not path.is_symlink() and not getattr(path,'is_junction',lambda:False)()
        def consider(owner, entity, kind, target, token=None):
            if not eligible(db,owner,entity,kind,token):self.counts['protected']+=1;return
            try: records=self.tree(target,kind)
            except (OSError,ValueError):self.counts['young_or_unsafe']+=1;return
            self.candidates.append(dict(kind=kind,owner=owner,entity=entity,token=token,
                location=target.relative_to(root).as_posix(),records=records,
                bytes=sum(record[4] for record in records if stat.S_ISREG(record[3]))))
        try:
            for owner in entries(root):
                if not canonical(owner.name) or not safe_dir(owner) or db.get(User,owner.name) is None:
                    self.counts['unrecognized']+=1;continue
                for child in entries(owner):
                    if not safe_dir(child):self.counts['unrecognized']+=1;continue
                    if child.name=='.uploads':
                        for session in entries(child):
                            if canonical(session.name) and safe_dir(session):consider(owner.name,session.name,'orphan-upload',session)
                            else:self.counts['unrecognized']+=1
                    elif canonical(child.name):
                        if db.get(RenderJob,child.name) is None and db.get(UploadSession,child.name) is None:
                            consider(owner.name,child.name,'orphan-media',child)
                        else:
                            self.counts['protected']+=1
                            for attempt in entries(child):
                                if canonical(attempt.name) and safe_dir(attempt):
                                    consider(owner.name,child.name,'stale-attempt',attempt,attempt.name)
                    else:self.counts['unrecognized']+=1
        except RetentionError:
            if not self.truncated:raise
        except OSError:self.counts['unreadable']+=1;self.truncated=True

    def s3(self, db):
        store.check_bucket()
        bucket=get_settings().s3_bucket;groups={};blocked=set()
        try:
            for namespace in ('media/','uploads/'):
                continuation=None;seen=set();pages=0
                while True:
                    pages+=1
                    if pages>100:self.truncated=True;raise RetentionError('page limit')
                    args=dict(Bucket=bucket,Prefix=namespace,MaxKeys=min(1000,self.scan_limit-self.scanned+1))
                    if continuation:args['ContinuationToken']=continuation
                    page=store.client().list_objects_v2(**args)
                    for obj in page.get('Contents',[]):
                        self.tick();key=obj['Key'];parts=key.split('/')
                        if len(parts)<4 or not canonical(parts[1]) or not canonical(parts[2]):
                            self.counts['unrecognized']+=1;continue
                        owner,entity=parts[1:3];token=None
                        if namespace=='media/' and db.get(RenderJob,entity) is not None:
                            if len(parts)!=5 or not canonical(parts[3]) or parts[4]!='output.mp4':
                                self.counts['protected']+=1;continue
                            kind='stale-attempt';token=parts[3]
                        else:kind='orphan-media' if namespace=='media/' else 'orphan-upload'
                        identity=(owner,entity,kind,token)
                        valid=(allowed_file('/'.join(parts[3:]),kind) if namespace=='media/' and kind!='stale-attempt' else
                            (len(parts)==5 and (parts[3] in ('incoming','sealed') if namespace=='uploads/' else canonical(parts[3])) and
                             (canonical(parts[4]) if namespace=='uploads/' else parts[4]=='output.mp4')))
                        if not eligible(db,owner,entity,kind,token,'s3'):self.counts['protected']+=1;continue
                        if not valid or aware(obj['LastModified'])>self.cutoff:blocked.add(identity);continue
                        groups.setdefault(identity,[]).append([key,obj['ETag'],obj['Size'],aware(obj['LastModified']).replace(microsecond=0).isoformat()])
                    next_token=page.get('NextContinuationToken')
                    if not page.get('IsTruncated'):break
                    if not next_token or next_token in seen:raise RetentionError('Incomplete S3 listing')
                    seen.add(next_token);continuation=next_token
        except RetentionError:
            if not self.truncated:raise
        for identity,records in groups.items():
            if identity in blocked:self.counts['young_or_unsafe']+=1;continue
            owner,entity,kind,token=identity
            self.candidates.append(dict(kind=kind,owner=owner,entity=entity,token=token,
                location=records[0][0].rsplit('/',1)[0],records=sorted(records),bytes=sum(record[2] for record in records)))

    def result(self):
        scope=store.namespace_id() if self.backend=='s3' else str(get_settings().storage_dir)
        identity=dict(backend=self.backend,scope=scope,database=engine.url.render_as_string(hide_password=True),
            grace_hours=self.grace_hours,scan_limit=self.scan_limit,candidates=sorted(self.candidates,key=lambda item:json.dumps(item,sort_keys=True)))
        digest=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        return dict(schema_version=1,backend=self.backend,grace_hours=self.grace_hours,
            scanned=min(self.scanned,self.scan_limit),truncated=self.truncated,digest=digest,
            candidate_groups=len(self.candidates),candidate_bytes=sum(item['bytes'] for item in self.candidates),
            skipped=dict(self.counts),candidates=identity['candidates'])


def preview(backend='local',grace_hours=24,scan_limit=10000,*,now=None):
    inventory=Inventory(backend,grace_hours,scan_limit,now or utcnow())
    try:
        with SessionLocal() as db:
            (inventory.local if backend=='local' else inventory.s3)(db)
    except (BotoCoreError,ClientError,ValueError,KeyError,TypeError,AttributeError) as error:
        raise RetentionError('Storage inventory unavailable') from error
    return inventory.result()


def apply(expected_digest, *, offline=False, backend='local',grace_hours=24,scan_limit=10000,now=None):
    if not offline:raise RetentionError('Stop all writers and explicitly use --offline before orphan removal')
    report=preview(backend,grace_hours,scan_limit,now=now)
    if report['truncated'] or report['digest']!=expected_digest:
        raise RetentionError('Preview changed or was incomplete; review a fresh complete preview')
    removed=failed=0
    for candidate in report['candidates']:
        try:
            with SessionLocal() as db:
                if not eligible(db,candidate['owner'],candidate['entity'],candidate['kind'],candidate['token'],backend):
                    raise RetentionError('Candidate became protected')
            if backend=='local':
                target=get_settings().storage_dir/candidate['location']
                # Recheck every ancestor and every metadata token before rmtree.
                for parent in [target,*target.parents]:
                    if parent==get_settings().storage_dir:break
                    if parent.is_symlink() or getattr(parent,'is_junction',lambda:False)():raise RetentionError('Unsafe ancestor')
                check=Inventory(backend,grace_hours,scan_limit,now or utcnow())
                if check.tree(target,candidate['kind'])!=candidate['records']:raise RetentionError('Candidate changed')
                shutil.rmtree(target)
            else:
                bucket=get_settings().s3_bucket
                for key,etag,size,modified in candidate['records']:
                    head=store.client().head_object(Bucket=bucket,Key=key)
                    if (head['ETag'],head['ContentLength'],aware(head['LastModified']).replace(microsecond=0).isoformat())!=(etag,size,modified):
                        raise RetentionError('Object changed')
                for key,_,_,_ in candidate['records']:store.client().delete_object(Bucket=bucket,Key=key)
            removed+=1
        except Exception:
            # No raw provider exception, customer path or signed URL in reports.
            failed+=1
    return {**report,'removed_groups':removed,'failed_groups':failed}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',choices=('local','s3'),default='local')
    parser.add_argument('--grace-hours',type=int,default=24)
    parser.add_argument('--scan-limit',type=int,default=10000)
    parser.add_argument('--apply',action='store_true');parser.add_argument('--offline',action='store_true')
    parser.add_argument('--expect-digest');parser.add_argument('--details',action='store_true')
    args=parser.parse_args()
    from .migrate import require_current_schema
    require_current_schema(engine)
    try:
        if args.apply and not args.expect_digest:raise RetentionError('Apply requires the reviewed preview digest')
        options=dict(backend=args.backend,grace_hours=args.grace_hours,scan_limit=args.scan_limit)
        result=apply(args.expect_digest,offline=args.offline,**options) if args.apply else preview(**options)
        if not args.details:result.pop('candidates')
        print(json.dumps(result,indent=2))
        if result.get('failed_groups'):raise SystemExit(1)
    except (RetentionError,store.ObjectStoreError):
        parser.exit(2,'Retention refused: incomplete/changed inventory, unsafe settings or unavailable store. Run a fresh preview; apply requires all writers offline.\n')


if __name__=='__main__':main()
