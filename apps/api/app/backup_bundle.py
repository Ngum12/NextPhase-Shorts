"""Streaming authenticated backup bundles; never extracts over an existing target.

Independent CURRENT journal/key/checkpoint custody remains required for replay.
This tool does not stop writers, fetch cloud data, or deploy a restored database.
"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path,PurePosixPath
import shutil
import stat
import struct
import tarfile
import uuid

from cryptography.fernet import Fernet,InvalidToken

MAGIC=b'NPBACKUP1\n';CHUNK=1024*1024;MAX_FRAME=2*CHUNK;MAX_ENTRIES=100000


class BackupError(RuntimeError):
    def __init__(self):super().__init__('Backup operation refused; verify key, integrity, source and new target')


def private_file(path):
    path=Path(path).absolute()
    if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (path,*path.parents)):raise BackupError()
    info=path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise BackupError()
    return path


def load_key(path):
    path=private_file(path);info=path.stat()
    if os.name=='posix' and (info.st_uid!=os.geteuid() or info.st_mode&0o077):raise BackupError()
    key=path.read_bytes()
    if len(key)>128:raise BackupError()
    try:return Fernet(key.strip())
    except (ValueError,TypeError):raise BackupError() from None


def generate_key(path):
    path=Path(path)
    if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in path.parents):raise BackupError()
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(descriptor,'wb') as out:out.write(Fernet.generate_key());out.flush();os.fsync(out.fileno())


class EncryptedWriter:
    def __init__(self,out,cipher,space_root=None):
        self.space_root=space_root;self.out=out;self.cipher=cipher;self.identity=uuid.uuid4().bytes;self.sequence=0;self.buffer=bytearray();self.digest=hashlib.sha256()
        out.write(MAGIC)
    def frame(self,kind,data):
        if self.space_root and shutil.disk_usage(self.space_root).free<CHUNK+16*1024*1024:raise BackupError()
        token=self.cipher.encrypt(self.identity+struct.pack('>Q',self.sequence)+kind+data)
        self.out.write(struct.pack('>I',len(token)));self.out.write(token);self.sequence+=1
    def write(self,data):
        self.digest.update(data);self.buffer.extend(data)
        while len(self.buffer)>=CHUNK:
            self.frame(b'D',bytes(self.buffer[:CHUNK]));del self.buffer[:CHUNK]
        return len(data)
    def finish(self):
        if self.buffer:self.frame(b'D',bytes(self.buffer));self.buffer.clear()
        self.frame(b'F',self.digest.digest());self.out.flush();os.fsync(self.out.fileno())


def decrypt(source,destination,cipher,*,max_bytes):
    if source.read(len(MAGIC))!=MAGIC:raise BackupError()
    identity=None;sequence=0;size=0;digest=hashlib.sha256()
    while True:
        header=source.read(4)
        if len(header)!=4:raise BackupError()
        length=struct.unpack('>I',header)[0]
        if not 100<=length<=MAX_FRAME:raise BackupError()
        token=source.read(length)
        if len(token)!=length:raise BackupError()
        try:plain=cipher.decrypt(token)
        except InvalidToken:raise BackupError() from None
        if len(plain)<25:raise BackupError()
        if identity is None:identity=plain[:16]
        if plain[:16]!=identity or struct.unpack('>Q',plain[16:24])[0]!=sequence:raise BackupError()
        sequence+=1;kind=plain[24:25];payload=plain[25:]
        if kind==b'F':
            if payload!=digest.digest() or source.read(1):raise BackupError()
            return size
        if kind!=b'D' or not payload or len(payload)>CHUNK:raise BackupError()
        size+=len(payload)
        if size>max_bytes:raise BackupError()
        if shutil.disk_usage(Path(destination.name).parent).free<len(payload)+16*1024*1024:raise BackupError()
        digest.update(payload);destination.write(payload)


def name_ok(name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name or '\x00' in name:return False
    parts=PurePosixPath(name).parts
    return not name.startswith('/') and all(part not in ('.','..','') for part in name.split('/')) and len(parts)<=20 and len(name)<=1024


def create(output,*,database_dump,media,journal,checkpoint,key_file,offline=False):
    from .restore_journal import canonical
    if not offline:raise BackupError()
    cipher=load_key(key_file);database=private_file(database_dump);media=Path(media).absolute()
    if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (media,*media.parents)) or not media.is_dir():raise BackupError()
    key=Path(key_file).absolute()
    with database.open('rb') as handle:signature=handle.read(16)
    if not (signature.startswith(b'PGDMP') or signature==b'SQLite format 3\x00') or database.samefile(key):raise BackupError()
    if key.is_relative_to(media) or key.is_relative_to(journal.root):raise BackupError()
    entries=[('database.dump',database)]
    for path in media.rglob('*'):
        if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise BackupError()
        if path.is_file():entries.append(('media/'+path.relative_to(media).as_posix(),private_file(path)))
        elif not path.is_dir():raise BackupError()
        if len(entries)>MAX_ENTRIES-4:raise BackupError()
    with journal.locked(read_only=True):
        if journal._read()[0]!=checkpoint or (journal.root/'restore-hold.json').exists():raise BackupError()
        entries.append(('snapshot-journal/events.jsonl',private_file(journal.root/'events.jsonl')))
        output=Path(output)
        if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in output.parents):raise BackupError()
        if output.absolute().is_relative_to(media) or output.absolute().is_relative_to(journal.root):raise BackupError()
        descriptor=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            with os.fdopen(descriptor,'wb') as handle:
                encrypted=EncryptedWriter(handle,cipher,output.parent);manifest={}
                with tarfile.open(fileobj=encrypted,mode='w|',format=tarfile.USTAR_FORMAT) as archive:
                    def add_bytes(name,data):
                        info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o600
                        archive.addfile(info,io.BytesIO(data))
                    for name,path in entries:
                        if not name_ok(name) or name.casefold() in manifest:raise BackupError()
                        before=path.stat();digest=hashlib.sha256()
                        with path.open('rb') as source:
                            while block:=source.read(CHUNK):digest.update(block)
                        info=tarfile.TarInfo(name);info.size=before.st_size;info.mode=0o600
                        with path.open('rb') as source:archive.addfile(info,source)
                        after=path.stat()
                        if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino):raise BackupError()
                        manifest[name.casefold()]={'name':name,'size':before.st_size,'sha256':digest.hexdigest()}
                    add_bytes('checkpoint.json',canonical(checkpoint))
                    manifest['checkpoint.json']={'name':'checkpoint.json','size':len(canonical(checkpoint)),'sha256':hashlib.sha256(canonical(checkpoint)).hexdigest()}
                    add_bytes('manifest.json',canonical({'version':1,'files':manifest,'journal_role':'snapshot only; current independent journal required for replay'}))
                if journal._read()[0]!=checkpoint:raise BackupError()
                encrypted.finish()
        except BaseException:
            output.unlink(missing_ok=True);raise
    return {'encrypted':True,'files':len(manifest),'key_in_bundle':False,'current_journal_replaces_snapshot':False}


def restore(bundle,output,key_file,*,max_bytes=100*1024**3):
    if not 1024<=max_bytes<=1024**4:raise BackupError()
    cipher=load_key(key_file);bundle=private_file(bundle);output=Path(output).absolute()
    # Exclusive new private directory; no replace/merge, no tar extraction helpers.
    if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in output.parents):raise BackupError()
    output.mkdir(mode=0o700)
    try:
        temporary=output/'authenticated.tar'
        with bundle.open('rb') as source,temporary.open('xb') as destination:
            os.chmod(temporary,0o600);size=decrypt(source,destination,cipher,max_bytes=max_bytes)
        if shutil.disk_usage(output).free<size+16*1024*1024:raise BackupError()
        found={};seen=set();manifest=None;total=0
        with tarfile.open(temporary,mode='r:') as archive:
            for index,member in enumerate(archive):
                if index>=MAX_ENTRIES or not member.isfile() or not name_ok(member.name) or member.name.casefold() in seen:raise BackupError()
                seen.add(member.name.casefold());total+=member.size
                if member.size<0 or total>max_bytes:raise BackupError()
                if member.name=='manifest.json':
                    if member.size>16*1024*1024:raise BackupError()
                    manifest=json.load(archive.extractfile(member));continue
                if not (member.name in ('database.dump','checkpoint.json','snapshot-journal/events.jsonl') or member.name.startswith('media/')):raise BackupError()
                path=output/member.name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                digest=hashlib.sha256();length=0
                with archive.extractfile(member) as source,path.open('xb') as destination:
                    os.chmod(path,0o600)
                    while block:=source.read(CHUNK):destination.write(block);digest.update(block);length+=len(block)
                found[member.name.casefold()]={'name':member.name,'size':length,'sha256':digest.hexdigest()}
        if not manifest or (type(manifest.get('version')) is not int or manifest.get('version')!=1) or manifest.get('files')!=found or not {'database.dump','checkpoint.json','snapshot-journal/events.jsonl'}<=set(found):raise BackupError()
        temporary.unlink()
        (output/'READY.json').write_text(json.dumps({'authenticated':True,'files':len(found),'deployable':False,'requires':'current independent journal, offline replay/release and target validation'})+'\n')
        os.chmod(output/'READY.json',0o600)
        return {'authenticated':True,'files':len(found),'database_deployed':False}
    except BaseException:
        shutil.rmtree(output);raise


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('keygen','create','restore'))
    parser.add_argument('--key-file',type=Path,required=True);parser.add_argument('--output',type=Path)
    parser.add_argument('--database-dump',type=Path);parser.add_argument('--media',type=Path)
    parser.add_argument('--checkpoint',type=Path);parser.add_argument('--bundle',type=Path);parser.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    try:
        if args.action=='keygen':generate_key(args.key_file);result={'key_created':True,'value_printed':False}
        elif args.action=='restore':result=restore(args.bundle,args.output,args.key_file)
        else:
            from .restore_journal import configured
            from .restore_replay import expected_checkpoint
            result=create(args.output,database_dump=args.database_dump,media=args.media,journal=configured(),checkpoint=expected_checkpoint(args.checkpoint),key_file=args.key_file,offline=args.offline)
        print(json.dumps(result))
    except Exception:parser.exit(1,'Backup operation refused; source, key and existing targets were preserved.\n')

if __name__=='__main__':main()
