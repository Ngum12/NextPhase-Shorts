"""Accepted-upload binding, private review lifecycle and migration regression."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import threading
import uuid

import pytest
from sqlalchemy import delete, select, text

from app.analysis_annotations import fingerprint
from app.analysis_plan import Transcript
from app.config import get_settings
from app.db import SessionLocal
from app.models import ProjectAnalysis, RenderJob
from app.project_analysis import import_transcript
from test_api import new_user
from test_migrations import migration_engine
from test_upload_sessions import create, fill


@pytest.fixture
def prepared(client, monkeypatch):
    settings=get_settings()
    owner={'Authorization':'Bearer '+new_user(client)}
    other={'Authorization':'Bearer '+new_user(client)}
    uid=client.get('/api/v1/me',headers=owner).json()['id']
    other_id=client.get('/api/v1/me',headers=other).json()['id']
    monkeypatch.setattr(settings,'english_review_enabled',True)
    monkeypatch.setattr(settings,'english_review_user_ids',(uid,other_id))
    monkeypatch.setattr(settings,'upload_chunk_bytes',8)
    monkeypatch.setattr('app.uploads.probe_video',lambda _:dict(duration=12,width=320,height=180))
    payload=b'original synthetic bytes'
    session=create(client,owner,total=len(payload)).json()['id']
    fill(client,owner,session,payload)
    completed=client.post(f'/api/v1/upload-sessions/{session}/complete',headers=owner)
    assert completed.status_code==200,completed.text
    jid=completed.json()['id']
    transcript=Transcript(source_sha256=hashlib.sha256(payload).hexdigest(),source_duration_ms=12000,
        language='en',provider='whisper_cpp',model_sha256='b'*64,engine_sha256='c'*64,
        timestamp_quality='model_token_estimate',words=tuple(dict(text=f'word{i}',
            start_ms=i*750,end_ms=i*750+700,confidence=.2 if i in (0,9) else .95) for i in range(16)))
    result=dict(owner=owner,other=other,uid=uid,jid=jid,transcript=transcript,
                url=f'/api/v1/jobs/{jid}/analysis')
    yield result
    with SessionLocal.begin() as db:
        db.execute(delete(ProjectAnalysis).where(ProjectAnalysis.job_id.in_(
            select(RenderJob.id).where(RenderJob.user_id==uid))))


def imported(prepared):
    with SessionLocal.begin() as db:
        import_transcript(db,owner=prepared['uid'],job_id=prepared['jid'],transcript=prepared['transcript'])


def annotations(prepared, ends=(8,16), confirmed=(1,10)):
    transcript=prepared['transcript']
    return dict(schema_version='transcript-review-1',source_sha256=transcript.source_sha256,
        transcript_sha256=fingerprint(transcript),acknowledged_original_recording=True,
        sentence_end_words=list(ends),confirmed_low_confidence_words=list(confirmed))


def saved_payload(client, prepared, **kwargs):
    document=client.get(prepared['url'],headers=prepared['owner']).json()
    return dict(revision=document['revision'],review=annotations(prepared,**kwargs))


def test_import_binds_actual_accepted_upload_and_preserves_native_provenance(client,prepared):
    imported(prepared)
    response=client.get(prepared['url'],headers=prepared['owner'])
    assert response.status_code==200 and response.headers['cache-control']=='private, no-store'
    data=response.json()
    assert data['transcript']==prepared['transcript'].model_dump(mode='json')
    assert data['review'] is None and not data['proposal']['candidates']
    assert not data['render_enabled'] and data['transcript_sha256']==fingerprint(prepared['transcript'])


def test_missing_disabled_unallowlisted_and_foreign_projects_are_private(client,prepared,monkeypatch):
    assert client.get(prepared['url'],headers=prepared['owner']).status_code==404
    imported(prepared)
    assert client.get(prepared['url']).status_code==401
    assert client.get(prepared['url'],headers=prepared['other']).status_code==404
    body=saved_payload(client,prepared)
    assert client.put(prepared['url']+'/review',headers=prepared['other'],json=body).status_code==404
    assert client.put(prepared['url']+'/review',json=body).status_code==401
    monkeypatch.setattr(get_settings(),'english_review_user_ids',())
    assert client.get(prepared['url'],headers=prepared['owner']).status_code==404
    monkeypatch.setattr(get_settings(),'english_review_enabled',False)
    assert client.put(prepared['url']+'/review',headers=prepared['owner'],json=body).status_code==404


@pytest.mark.parametrize('mutation',['source','duration','language','words','size','unaccepted'])
def test_import_rejects_wrong_source_language_and_bounds(prepared,mutation,monkeypatch):
    data=prepared['transcript'].model_dump()
    if mutation=='source':data['source_sha256']='0'*64
    if mutation=='duration':data['source_duration_ms']=13000
    if mutation=='language':data['language']='fr'
    if mutation=='words':monkeypatch.setattr('app.project_analysis.MAX_WORDS',1)
    if mutation=='size':monkeypatch.setattr('app.project_analysis.MAX_TRANSCRIPT_BYTES',1)
    with SessionLocal.begin() as db:
        if mutation=='unaccepted':
            from app.models import UploadSession
            db.scalar(select(UploadSession).where(UploadSession.job_id==prepared['jid'])).status='aborted'
            db.flush()
        with pytest.raises(ValueError):
            import_transcript(db,owner=prepared['uid'],job_id=prepared['jid'],
                              transcript=Transcript.model_validate(data))
        assert db.get(ProjectAnalysis,prepared['jid']) is None


@pytest.mark.parametrize('limit',['MAX_OWNER_ROWS','MAX_GLOBAL_ROWS'])
def test_metadata_pool_is_bounded(prepared,monkeypatch,limit):
    monkeypatch.setattr('app.project_analysis.'+limit,0)
    with SessionLocal.begin() as db:
        with pytest.raises(ValueError,match='capacity'):
            import_transcript(db,owner=prepared['uid'],job_id=prepared['jid'],transcript=prepared['transcript'])


def test_review_uses_boundaries_without_rewriting_words_or_scores(client,prepared):
    imported(prepared);body=saved_payload(client,prepared)
    response=client.put(prepared['url']+'/review',headers=prepared['owner'],json=body)
    assert response.status_code==200,response.text
    data=response.json()
    assert data['proposal']['algorithm']=='sentence-window-v3-reviewed'
    assert data['proposal']['candidates'] and data['review']==body['review']
    assert data['transcript']==prepared['transcript'].model_dump(mode='json')
    assert all(c['output_frames']<=450 for c in data['proposal']['candidates'])
    assert data['proposal']['review_sha256'] and data['proposal']['human_review_required']
    assert not data['proposal']['semantic_quality_verified'] and not data['render_enabled']


def test_unconfirmed_word_still_blocks_its_sentence(client,prepared):
    imported(prepared);body=saved_payload(client,prepared,confirmed=(1,))
    response=client.put(prepared['url']+'/review',headers=prepared['owner'],json=body)
    assert response.status_code==200
    assert all(c['last_word']<8 for c in response.json()['proposal']['candidates'])
    assert response.json()['proposal']['candidates']


@pytest.mark.parametrize('mutation',['source','digest','missing','duplicate','unsorted','not_flagged','ack','extra'])
def test_invalid_review_is_refused_without_echoing_payload(client,prepared,mutation,caplog):
    imported(prepared);body=saved_payload(client,prepared);review=body['review']
    if mutation=='source':review['source_sha256']='0'*64
    if mutation=='digest':review['transcript_sha256']='0'*64
    if mutation=='missing':review['sentence_end_words']=[1000]
    if mutation=='duplicate':review['sentence_end_words']=[8,8]
    if mutation=='unsorted':review['sentence_end_words']=[16,8]
    if mutation=='not_flagged':review['confirmed_low_confidence_words']=[2]
    if mutation=='ack':review['acknowledged_original_recording']=False
    if mutation=='extra':review['text']='private-text-must-not-echo'
    response=client.put(prepared['url']+'/review',headers=prepared['owner'],json=body)
    assert response.status_code==422,response.text
    assert 'private-text-must-not-echo' not in response.text+caplog.text
    assert response.headers['cache-control'] in ('private, no-store','no-store')
    with SessionLocal() as db:assert db.get(ProjectAnalysis,prepared['jid']).review_json is None


def test_oversize_review_is_rejected_before_validation(client,prepared):
    imported(prepared)
    response=client.put(prepared['url']+'/review',headers={**prepared['owner'],'Content-Type':'application/json'},
        content='{"padding":"'+'x'*70000+'"}')
    assert response.status_code==413


def test_lost_response_retry_and_stale_edit_fencing(client,prepared):
    imported(prepared);first=saved_payload(client,prepared)
    initial=client.put(prepared['url']+'/review',headers=prepared['owner'],json=first)
    retry=client.put(prepared['url']+'/review',headers=prepared['owner'],json=first)
    assert initial.status_code==retry.status_code==200
    assert initial.json()['revision']==retry.json()['revision']
    next_body=dict(revision=initial.json()['revision'],review=annotations(prepared,ends=(7,16)))
    changed=client.put(prepared['url']+'/review',headers=prepared['owner'],json=next_body)
    assert changed.status_code==200
    assert client.put(prepared['url']+'/review',headers=prepared['owner'],json=first).status_code==409
    assert client.get(prepared['url'],headers=prepared['owner']).json()['review']==next_body['review']


def test_identical_reimport_preserves_review_and_changed_transcript_is_refused(client,prepared):
    imported(prepared);body=saved_payload(client,prepared)
    saved=client.put(prepared['url']+'/review',headers=prepared['owner'],json=body).json()
    imported(prepared)
    assert client.get(prepared['url'],headers=prepared['owner']).json()==saved
    changed=prepared['transcript'].model_dump();changed['words'][0]['text']='different'
    with SessionLocal.begin() as db:
        with pytest.raises(ValueError,match='preserved'):
            import_transcript(db,owner=prepared['uid'],job_id=prepared['jid'],transcript=Transcript.model_validate(changed))


@pytest.mark.parametrize('kind',['project','account'])
def test_deletion_erases_review_and_blocks_reads_and_writes(client,prepared,kind):
    imported(prepared);body=saved_payload(client,prepared)
    if kind=='project':
        response=client.delete('/api/v1/jobs/'+prepared['jid'],headers=prepared['owner'])
    else:
        response=client.post('/api/v1/account/delete',headers=prepared['owner'],
            json={'current_password':'correct horse battery staple','receipt_key':str(uuid.uuid4())})
    assert response.status_code==202,response.text
    with SessionLocal() as db:assert db.get(ProjectAnalysis,prepared['jid']) is None
    assert client.get(prepared['url'],headers=prepared['owner']).status_code in (401,404)
    assert client.put(prepared['url']+'/review',headers=prepared['owner'],json=body).status_code in (401,404)


def test_two_concurrent_edits_cannot_overwrite_each_other(client,prepared):
    imported(prepared);first=saved_payload(client,prepared);second=deepcopy(first)
    second['review']['sentence_end_words']=[7,16]
    barrier=threading.Barrier(2)
    def save(body):
        barrier.wait(timeout=10)
        return client.put(prepared['url']+'/review',headers=prepared['owner'],json=body).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save,(first,second)))==[200,409]


def test_concurrent_delete_and_review_cannot_resurrect_analysis(client,prepared):
    imported(prepared);body=saved_payload(client,prepared);barrier=threading.Barrier(2)
    def save():
        barrier.wait(timeout=10)
        return client.put(prepared['url']+'/review',headers=prepared['owner'],json=body).status_code
    def remove():
        barrier.wait(timeout=10)
        return client.delete('/api/v1/jobs/'+prepared['jid'],headers=prepared['owner']).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        saved=pool.submit(save);removed=pool.submit(remove)
        assert saved.result() in (200,404) and removed.result()==202
    with SessionLocal() as db:assert db.get(ProjectAnalysis,prepared['jid']) is None


@pytest.mark.parametrize('kind',['project_delete','account_delete'])
def test_restore_replay_erases_analysis_tombstones(prepared,kind):
    from app.restore_replay import apply_records
    imported(prepared)
    record=dict(kind=kind,owner=prepared['uid'],project=prepared['jid'] if kind=='project_delete' else None,
                backend='local' if kind=='project_delete' else None,namespace=None if kind=='project_delete' else [])
    with SessionLocal.begin() as db:
        apply_records(db,[record])
        assert db.get(ProjectAnalysis,prepared['jid']) is None


def test_upgrade_from_0020_preserves_data_and_adds_empty_review_table(migration_engine):
    from alembic import command
    from app.migrate import configuration,require_current_schema,upgrade_schema
    with migration_engine.begin() as connection:
        command.upgrade(configuration(connection),'0020_restore_binding')
        connection.execute(text("INSERT INTO users (id,email,password_hash,created_at) VALUES ('keep-owner','keep@example.com','keep-hash',CURRENT_TIMESTAMP)"))
        connection.execute(RenderJob.__table__.insert().values(id='keep-project',user_id='keep-owner',
            title='Keep this result',style='vlog',desired_seconds=15,source_duration_seconds=12,
            source_path='input.mp4',output_path='output.mp4',status='succeeded'))
    upgrade_schema(migration_engine);require_current_schema(migration_engine)
    with migration_engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM project_analyses'))==0
        assert connection.scalar(text("SELECT email FROM users WHERE id='keep-owner'"))=='keep@example.com'
        assert connection.execute(text("SELECT title,status,output_path FROM render_jobs WHERE id='keep-project'")).one()==('Keep this result','succeeded','output.mp4')


@pytest.mark.parametrize('env,owners',[('production',str(uuid.uuid4())),('staging',str(uuid.uuid4())),
                                    ('test',''),('test','not-a-user-uuid')])
def test_configuration_refuses_public_or_unscoped_review(monkeypatch,env,owners):
    from app.config import Settings
    monkeypatch.setenv('APP_ENV',env)
    monkeypatch.setenv('ENGLISH_REVIEW_ENABLED','true')
    monkeypatch.setenv('ENGLISH_REVIEW_USER_IDS',owners)
    with pytest.raises(RuntimeError,match='English review pilot'):Settings()


def test_save_rate_limit_is_enforced_without_changing_review(client,prepared):
    imported(prepared);body=saved_payload(client,prepared)
    for _ in range(60):
        assert client.put(prepared['url']+'/review',headers=prepared['owner'],json=body).status_code==200
    response=client.put(prepared['url']+'/review',headers=prepared['owner'],json=body)
    assert response.status_code==429
    assert client.get(prepared['url'],headers=prepared['owner']).json()['review']==body['review']


def test_real_media_upload_import_and_review_round_trip(client,monkeypatch,tmp_path):
    """Real FFprobe/upload binding; manual fixture words are not ASR evidence."""
    import math
    import subprocess
    from app.media import probe_video
    from test_upload_sessions import put
    source=tmp_path/'original.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-n','-f','lavfi','-i',
        'testsrc2=size=160x90:rate=15','-t','12','-c:v','libx264','-threads','2',
        '-pix_fmt','yuv420p',str(source)],check=True,timeout=30)
    owner={'Authorization':'Bearer '+new_user(client)}
    uid=client.get('/api/v1/me',headers=owner).json()['id']
    monkeypatch.setattr(get_settings(),'english_review_enabled',True)
    monkeypatch.setattr(get_settings(),'english_review_user_ids',(uid,))
    payload=source.read_bytes()
    session=create(client,owner,total=len(payload)).json()['id']
    assert put(client,owner,session,0,payload).status_code==200
    response=client.post(f'/api/v1/upload-sessions/{session}/complete',headers=owner)
    assert response.status_code==200,response.text
    jid=response.json()['id']
    transcript=Transcript(source_sha256=hashlib.sha256(payload).hexdigest(),
        source_duration_ms=math.ceil(probe_video(source)['duration']*1000),language='en',
        provider='manual',timestamp_quality='operator_supplied',words=tuple(dict(text=f'word{i}',
            start_ms=i*750,end_ms=i*750+700,confidence=.2 if i==0 else .9) for i in range(16)))
    item=dict(owner=owner,uid=uid,jid=jid,transcript=transcript,url=f'/api/v1/jobs/{jid}/analysis')
    imported(item)
    body=saved_payload(client,item,confirmed=(1,))
    saved=client.put(item['url']+'/review',headers=owner,json=body)
    assert saved.status_code==200 and saved.json()['proposal']['candidates']
    assert saved.json()['transcript']['provider']=='manual'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==transcript.source_sha256
    assert client.delete('/api/v1/jobs/'+jid,headers=owner).status_code==202


@pytest.mark.parametrize('invalid',[False,True])
def test_operator_stdin_cli_import_is_bounded_and_prints_no_transcript(prepared,invalid):
    import json
    import os
    import subprocess
    import sys
    env={**os.environ,'ENGLISH_REVIEW_ENABLED':'true','ENGLISH_REVIEW_USER_IDS':prepared['uid']}
    content='x'*262145 if invalid else prepared['transcript'].model_dump_json()
    response=subprocess.run([sys.executable,'-m','app.project_analysis','--owner',prepared['uid'],
        '--project',prepared['jid'],'--stdin-transcript'],input=content,text=True,capture_output=True,
        env=env,timeout=30)
    result=json.loads(response.stdout)
    assert result['ok'] is (not invalid)
    assert response.returncode==int(invalid)
    assert 'word0' not in response.stdout+response.stderr
    with SessionLocal() as db:
        assert (db.get(ProjectAnalysis,prepared['jid']) is not None) is (not invalid)
