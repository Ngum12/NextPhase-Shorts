import io
import json
import os
import shutil
from pathlib import Path
import struct
import tarfile
from cryptography.fernet import Fernet
import pytest
from app.backup_bundle import BackupError,EncryptedWriter,create,restore,generate_key,CHUNK
from app.restore_journal import Journal


@pytest.fixture
def bundle_fixture(tmp_path):
    key=tmp_path/'separate-key';generate_key(key)
    journal=Journal(tmp_path/'independent',Fernet.generate_key().decode());journal.initialize()
    media=tmp_path/'media';media.mkdir();(media/'input.mp4').write_bytes(b'private-video-fixture'*100000)
    database=tmp_path/'database.dump';database.write_bytes(b'PGDMP'+b'private-database-fixture'*100)
    output=tmp_path/'backup.npb'
    create(output,database_dump=database,media=media,journal=journal,checkpoint=journal.checkpoint(),key_file=key,offline=True)
    try:yield tmp_path,key,journal,media,database,output
    finally:shutil.rmtree(tmp_path,ignore_errors=True)


def test_encrypted_roundtrip_streams_multiple_frames_and_keeps_key_separate(bundle_fixture):
    root,key,journal,media,database,output=bundle_fixture
    data=output.read_bytes()
    assert b'private-video-fixture' not in data and key.read_bytes() not in data
    result=restore(output,root/'recovered',key)
    assert result['authenticated'] and not result['database_deployed']
    assert (root/'recovered/media/input.mp4').read_bytes()==(media/'input.mp4').read_bytes()
    assert (root/'recovered/database.dump').read_bytes()==database.read_bytes()
    assert journal.checkpoint()['count']==0
    assert not (root/'recovered/journal.key').exists()
    assert (root/'recovered/READY.json').exists()


@pytest.mark.parametrize('damage',['flip','truncate','append','reorder','duplicate','wrong-key','oversize'])
def test_invalid_bundle_never_publishes_restored_files(bundle_fixture,damage):
    root,key,_,_,_,output=bundle_fixture;raw=bytearray(output.read_bytes())
    if damage=='flip':raw[len(raw)//2]^=1
    elif damage=='truncate':raw=raw[:-15]
    elif damage=='append':raw+=b'garbage'
    elif damage in ('reorder','duplicate'):
        prefix=10;length=struct.unpack('>I',raw[prefix:prefix+4])[0];first=raw[prefix:prefix+4+length];rest=raw[prefix+4+length:]
        if damage=='duplicate':raw=raw[:prefix]+first+first+rest
        else:raw=raw[:prefix]+rest+first
    elif damage=='wrong-key':key=root/'other-key';generate_key(key)
    output.write_bytes(raw)
    with pytest.raises(Exception):restore(output,root/'bad',key,max_bytes=1024 if damage=='oversize' else 100*1024**3)
    assert not (root/'bad').exists()


def test_restore_refuses_existing_directory_and_create_preserves_existing_file(bundle_fixture):
    root,key,journal,media,database,output=bundle_fixture
    destination=root/'existing';destination.mkdir();(destination/'keep').write_text('preserve')
    with pytest.raises(FileExistsError):restore(output,destination,key)
    before=output.read_bytes()
    with pytest.raises(Exception):create(output,database_dump=database,media=media,journal=journal,checkpoint=journal.checkpoint(),key_file=key,offline=True)
    assert (destination/'keep').read_text()=='preserve' and output.read_bytes()==before


@pytest.mark.parametrize('name,typecode',[('..'+ '/escape',tarfile.REGTYPE),('media/link',tarfile.SYMTYPE),('/absolute',tarfile.REGTYPE),('media\\escape',tarfile.REGTYPE)])
def test_authenticated_malicious_archive_cannot_escape_target(bundle_fixture,name,typecode):
    root,key,_,_,_,_=bundle_fixture;output=root/'malicious.npb'
    with output.open('wb') as file:
        writer=EncryptedWriter(file,Fernet(key.read_bytes()))
        with tarfile.open(fileobj=writer,mode='w|') as archive:
            item=tarfile.TarInfo(name);item.type=typecode;item.size=1 if typecode==tarfile.REGTYPE else 0;item.linkname='../outside'
            archive.addfile(item,io.BytesIO(b'x') if item.size else None)
        writer.finish()
    with pytest.raises(BackupError):restore(output,root/'recovered-malicious',key)
    assert not (root/'escape').exists() and not (root/'recovered-malicious').exists()


def test_snapshot_checkpoint_and_offline_ack_required(bundle_fixture):
    root,key,journal,media,database,_=bundle_fixture
    with pytest.raises(BackupError):create(root/'new',database_dump=database,media=media,journal=journal,checkpoint=journal.checkpoint(),key_file=key)
    checkpoint=journal.checkpoint();checkpoint['head']='f'*64
    with pytest.raises(BackupError):create(root/'new',database_dump=database,media=media,journal=journal,checkpoint=checkpoint,key_file=key,offline=True)
