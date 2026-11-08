"""Opt-in, independent encrypted write-ahead security journal. Linux local storage.

Not a remote vault or automatic restore detector. Keep outside DB/media snapshots.
A separately retained current checkpoint is required to detect rollback/truncation.
"""
import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import stat
import time
import uuid

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from .config import get_settings

MAX_BYTES=64*1024*1024
MAX_RECORDS=100000
ZERO='0'*64


class JournalError(RuntimeError):
    def __init__(self):super().__init__('Restore journal is unavailable or invalid')


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def identity(value):return isinstance(value,str) and str(uuid.UUID(value))==value


class Journal:
    def __init__(self,root,key):
        self.root=Path(root).absolute()
        try:
            self.cipher=Fernet(key.encode())
            self.mac_key=hmac.new(base64.urlsafe_b64decode(key),b'nextphase-restore-chain-v1',hashlib.sha256).digest()
        except Exception:raise JournalError() from None

    def safe(self,path,*,directory=False):
        if any(p.is_symlink() for p in (path,*path.parents)):raise JournalError()
        metadata=path.stat()
        if not (stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)):raise JournalError()
        if metadata.st_uid!=os.geteuid() or metadata.st_mode & 0o077:raise JournalError()
        if not directory and metadata.st_nlink!=1:raise JournalError()

    @contextmanager
    def locked(self,*,read_only=False):
        try:
            import fcntl
            self.safe(self.root,directory=True)
            self.safe(self.root/'lock')
            descriptor=os.open(self.root/'lock',(os.O_RDONLY if read_only else os.O_RDWR)|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(descriptor,'rb' if read_only else 'r+b') as handle:
                deadline=time.monotonic()+5
                while True:
                    try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                    except BlockingIOError:
                        if time.monotonic()>=deadline:raise JournalError()
                        time.sleep(.02)
                yield
        except (OSError,ValueError,ImportError,InvalidToken,KeyError,TypeError,json.JSONDecodeError):
            raise JournalError() from None

    def _read(self):
        path=self.root/'events.jsonl';self.safe(path)
        with path.open('rb') as handle:data=handle.read(MAX_BYTES+1)
        if not data or len(data)>MAX_BYTES or not data.endswith(b'\n'):raise JournalError()
        records=[];previous=ZERO;journal_id=None
        lines=data.splitlines()
        if len(lines)>MAX_RECORDS:raise JournalError()
        for index,line in enumerate(lines):
            row=json.loads(line)
            if set(row)!={'id','seq','prev','payload','mac'}:raise JournalError()
            mac=row.pop('mac')
            if not isinstance(mac,str) or not hmac.compare_digest(mac,hmac.new(self.mac_key,canonical(row),hashlib.sha256).hexdigest()):raise JournalError()
            if type(row['seq']) is not int or row['seq']!=index or row['prev']!=previous or not identity(row['id']):raise JournalError()
            if journal_id is not None and row['id']!=journal_id:raise JournalError()
            journal_id=row['id'];previous=mac
            payload=json.loads(self.cipher.decrypt(row['payload'].encode()))
            if index==0:
                if payload!={'kind':'genesis','schema_version':1}:raise JournalError()
            else:self.validate(payload)
            records.append(payload)
        return {'schema_version':1,'journal_id':journal_id,'count':len(records)-1,'head':previous},records[1:]

    @staticmethod
    def validate(payload):
        if set(payload)!={'kind','owner','project','backend','namespace'}:raise JournalError()
        if payload['kind'] not in ('revoke','password','account_delete','project_delete') or not identity(payload['owner']):raise JournalError()
        if payload['kind']=='project_delete':
            if not identity(payload['project']) or payload['backend'] not in ('local','s3'):raise JournalError()
            if payload['backend']=='s3' and not Journal.namespace(payload['namespace']):raise JournalError()
        elif payload['kind']=='account_delete':
            if payload['project'] is not None or payload['backend'] is not None or not isinstance(payload['namespace'],list) or len(payload['namespace'])>100 or not all(Journal.namespace(value) for value in payload['namespace']):raise JournalError()
        elif any(payload[key] is not None for key in ('project','backend','namespace')):raise JournalError()

    @staticmethod
    def namespace(value):
        return isinstance(value,str) and (value=='unknown' or (len(value)==64 and all(c in '0123456789abcdef' for c in value)))

    def _line(self,journal_id,seq,previous,payload):
        row={'id':journal_id,'seq':seq,'prev':previous,'payload':self.cipher.encrypt(canonical(payload)).decode()}
        row['mac']=hmac.new(self.mac_key,canonical(row),hashlib.sha256).hexdigest()
        return canonical(row)+b'\n'

    def initialize(self):
        # Explicit create only. Never initialize automatically after losing a journal.
        try:
            if any(p.is_symlink() for p in (self.root,*self.root.parents)):raise JournalError()
            self.root.mkdir(mode=0o700)
            for name in ('lock','events.jsonl'):
                descriptor=os.open(self.root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                with os.fdopen(descriptor,'wb') as handle:
                    if name=='events.jsonl':handle.write(self._line(str(uuid.uuid4()),0,ZERO,{'kind':'genesis','schema_version':1}))
                    handle.flush();os.fsync(handle.fileno())
            self.sync_directory()
        except (OSError,ValueError):raise JournalError() from None
        return self.checkpoint()

    def sync_directory(self):
        descriptor=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)

    def ready(self):
        with self.locked():
            if (self.root/'restore-hold.json').exists():raise JournalError()
            return self._read()[0]

    def checkpoint(self):
        with self.locked(read_only=True):return self._read()[0]

    def append(self,payload):
        self.validate(payload)
        with self.locked():
            if (self.root/'restore-hold.json').exists():raise JournalError()
            checkpoint,_=self._read()
            line=self._line(checkpoint['journal_id'],checkpoint['count']+1,checkpoint['head'],payload)
            path=self.root/'events.jsonl'
            if checkpoint['count']+2>MAX_RECORDS or path.stat().st_size+len(line)>MAX_BYTES:raise JournalError()
            descriptor=os.open(path,os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW)
            with os.fdopen(descriptor,'ab') as handle:
                handle.write(line);handle.flush();os.fsync(handle.fileno())


def configured():
    settings=get_settings()
    if not settings.restore_journal_dir:
        if settings.env in ('staging','production'):raise JournalError()
        return None
    root=Path(settings.restore_journal_dir).absolute()
    storage=settings.storage_dir.absolute()
    if root.is_relative_to(storage) or storage.is_relative_to(root):raise JournalError()
    return Journal(root,settings.restore_journal_key)


def record(kind,owner,*,project=None,backend=None,namespace=None):
    journal=configured()
    if journal is None:return  # Explicitly unprotected development; not staging acceptance.
    try:journal.append({'kind':kind,'owner':owner,'project':project,'backend':backend,'namespace':namespace})
    except (JournalError,OSError,ValueError):
        raise HTTPException(503,'Security change could not be recorded. Please retry.',headers={'Cache-Control':'no-store'}) from None


class RestoreGate:
    """A restore hold denies HTTP traffic even if a process was left running.

    This is a last guard, not coordination with active writers: replay still
    requires a stopped, isolated target. Full integrity is checked on readiness.
    """
    def __init__(self,app):self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type']=='http' and scope.get('path')!='/health':
            try:
                journal=configured()
                if journal:
                    journal.safe(journal.root,directory=True)
                    path=journal.root/'restore-hold.json'
                    if path.exists() or path.is_symlink():raise JournalError()
            except (JournalError,OSError):
                from starlette.responses import JSONResponse
                response=JSONResponse({'detail':'Service is temporarily unavailable'},status_code=503,headers={'Cache-Control':'no-store'})
                await response(scope,receive,send);return
        await self.app(scope,receive,send)
