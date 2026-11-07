import uuid
from datetime import timedelta
import pytest
from sqlalchemy import select
from app.db import SessionLocal
from app.models import RenderJob,UploadSession,utcnow
from app.consent import RIGHTS_VERSION
from test_api import new_user
from test_upload_sessions import context,create,fill,put
from upload_fixtures import RIGHTS_FORM,RIGHTS_JSON


def headers(token):return {'Authorization':'Bearer '+token}


@pytest.mark.parametrize('value',[None,False,'true',1])
def test_new_session_requires_strict_affirmative_acknowledgement(client,value):
    owner=headers(new_user(client));payload={'file_name':'source.mp4','total_bytes':24,'consent_version':RIGHTS_VERSION}
    if value is not None:payload['rights_confirmed']=value
    response=client.post('/api/v1/upload-sessions',headers={**owner,'Idempotency-Key':uuid.uuid4().hex},json=payload)
    assert response.status_code==422
    assert client.get('/api/v1/me/storage',headers=owner).json()['known_reserved_bytes']==0


@pytest.mark.parametrize('form',[{}, {'rights_confirmed':'false','consent_version':RIGHTS_VERSION},
                                 {'rights_confirmed':'true','consent_version':'unknown'}])
def test_legacy_upload_rejects_missing_false_or_unknown_ack(client,form):
    owner=headers(new_user(client))
    response=client.post('/api/v1/jobs',headers=owner,data=form,files={'file':('source.mp4',b'fake','video/mp4')})
    assert response.status_code==422
    assert client.get('/api/v1/jobs',headers=owner).json()==[]


def test_version_timestamp_is_stable_and_copied_to_job(client,context):
    owner,_,_=context
    key=uuid.uuid4().hex;session=create(client,owner,total=24,key=key).json();sid=session['id']
    original=session['rights_confirmed_at'];assert original and session['rights_version']==RIGHTS_VERSION
    assert create(client,owner,total=24,key=key).json()['rights_confirmed_at']==original
    fill(client,owner,sid,b'abcdefghijklmnopqrstuvwx')
    result=client.post(f'/api/v1/upload-sessions/{sid}/complete',headers=owner)
    assert result.status_code==200
    with SessionLocal() as db:
        source=db.get(UploadSession,sid);job=db.get(RenderJob,result.json()['id'])
        assert job.rights_version==RIGHTS_VERSION and job.rights_confirmed_at==source.rights_confirmed_at


def test_old_paused_session_requires_reconfirmation_without_losing_progress(client,context):
    owner,other,_=context;key=uuid.uuid4().hex
    sid=create(client,owner,total=24,key=key).json()['id']
    fill(client,owner,sid,b'abcdefghijklmnopqrstuvwx')
    with SessionLocal.begin() as db:
        row=db.get(UploadSession,sid);row.rights_version=None;row.rights_confirmed_at=None
    assert client.post(f'/api/v1/upload-sessions/{sid}/complete',headers=owner).status_code==409
    assert put(client,owner,sid,0,b'abcdefgh').status_code==409
    assert client.get('/api/v1/upload-sessions/by-key/'+key,headers=other).status_code==404
    replay=create(client,owner,total=24,key=key)
    assert replay.status_code==200 and replay.json()['id']==sid
    assert replay.json()['received_bytes']==24 and replay.json()['rights_confirmed_at']
    assert client.post(f'/api/v1/upload-sessions/{sid}/complete',headers=owner).status_code==200


def test_unacknowledged_saved_upload_can_be_looked_up_and_discarded(client,context):
    owner,_,_=context;key=uuid.uuid4().hex;sid=create(client,owner,key=key).json()['id']
    with SessionLocal.begin() as db:
        row=db.get(UploadSession,sid);row.rights_version=None;row.rights_confirmed_at=None
    assert client.get('/api/v1/upload-sessions/by-key/'+key,headers=owner).json()['id']==sid
    assert client.post(f'/api/v1/upload-sessions/{sid}/abort',headers=owner).status_code==200
    with SessionLocal() as db:assert db.get(UploadSession,sid).rights_confirmed_at is None


def test_legacy_upload_persists_server_acknowledgement(client,context):
    owner,_,_=context
    response=client.post('/api/v1/jobs',headers=owner,data=RIGHTS_FORM,files={'file':('source.mp4',b'fake','video/mp4')})
    assert response.status_code==201
    with SessionLocal() as db:
        row=db.get(RenderJob,response.json()['id'])
        assert row.rights_version==RIGHTS_VERSION and row.rights_confirmed_at


def test_mobile_and_server_use_the_same_versioned_statement():
    from pathlib import Path
    from app.consent import RIGHTS_TEXT
    source=(Path(__file__).resolve().parents[3]/'apps/mobile/src/uploadRights.ts').read_text()
    assert RIGHTS_VERSION in source and RIGHTS_TEXT in source


def test_discard_by_key_needs_no_assertion_and_fences_late_creation(client,context):
    owner,_,_=context;key=uuid.uuid4().hex
    result=client.post('/api/v1/upload-sessions/discard-by-key',headers={**owner,'Idempotency-Key':key})
    assert result.status_code==200 and result.json()['status']=='aborted'
    assert result.json()['total_bytes']==0 and result.json()['rights_confirmed_at'] is None
    assert client.get('/api/v1/me/storage',headers=owner).json()['known_reserved_bytes']==0
    assert create(client,owner,key=key).status_code==410
    assert client.post('/api/v1/upload-sessions/discard-by-key',headers={**owner,'Idempotency-Key':key}).status_code==200


def test_discard_and_create_race_never_reopens_the_intent(client,context):
    from concurrent.futures import ThreadPoolExecutor
    from app.models import UploadSession
    owner,_,owner_id=context;key=uuid.uuid4().hex
    with ThreadPoolExecutor(max_workers=2) as pool:
        new=pool.submit(create,client,owner,key=key)
        discard=pool.submit(client.post,'/api/v1/upload-sessions/discard-by-key',headers={**owner,'Idempotency-Key':key})
        assert discard.result().status_code==200
        assert new.result().status_code in (201,410)
    with SessionLocal() as db:
        row=db.scalar(select(UploadSession).where(UploadSession.user_id==owner_id,UploadSession.client_key==key))
        assert row.status=='aborted'
        assert put(client,owner,row.id,0,b'abcdefgh').status_code==409
