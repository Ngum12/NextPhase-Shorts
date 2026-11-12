"""Owner-bound reviewed excerpt admission, worker output and deletion fencing."""
from datetime import timedelta
import hashlib
import math
from pathlib import Path
import subprocess
import uuid

import pytest
from sqlalchemy import select, update

from app.analysis_annotations import fingerprint
from app.analysis_plan import Transcript
from app.config import get_settings
from app.db import SessionLocal
from app.models import ProjectAnalysis, RenderAttempt, RenderJob, utcnow
from app.project_analysis import import_transcript
from test_project_analysis import prepared, imported, saved_payload
from test_api import new_user
from test_upload_sessions import create, put
from test_restore_journal import journal
from test_migrations import migration_engine


def review(client,item):
    imported(item)
    response=client.put(item['url']+'/review',headers=item['owner'],json=saved_payload(client,item))
    assert response.status_code==200,response.text
    return response.json()


def request(client,item,data,*,key=None,number=1,ack=True,caption_style='none',framing='fit'):
    return client.post(item['url']+'/previews',headers=item['owner'],json=dict(
        revision=data['revision'],candidate_number=number,idempotency_key=key or str(uuid.uuid4()),
        acknowledged_preview=ack,caption_style=caption_style,framing=framing))


def test_admission_is_source_bound_immutable_budgeted_and_replayable(client,prepared):
    data=review(client,prepared);key=str(uuid.uuid4())
    first=request(client,prepared,data,key=key);assert first.status_code==202,first.text
    replay=request(client,prepared,data,key=key)
    assert replay.status_code==202 and replay.json()['id']==first.json()['id']
    assert first.json()['preview_parent_id']==prepared['jid']
    with SessionLocal() as db:
        child=db.get(RenderJob,first.json()['id'])
        from app.excerpt_jobs import ExcerptSpec
        spec=ExcerptSpec.model_validate_json(child.preview_spec_json)
        assert spec.source_sha256==prepared['transcript'].source_sha256
        assert spec.review_revision==data['revision'] and spec.output_frames<=450
        assert child.storage_reserved_bytes==2*spec.source_bytes+2*child.max_render_bytes
        assert not child.source_path and child.media_backend=='local'
        assert child.rights_version==db.get(RenderJob,prepared['jid']).rights_version
    assert request(client,prepared,data,key=key,number=2).status_code==409
    next_review=saved_payload(client,prepared,ends=(7,16))
    assert client.put(prepared['url']+'/review',headers=prepared['owner'],json=next_review).status_code==200
    # An acknowledged immutable request still recovers its result after a later review.
    assert request(client,prepared,data,key=key).json()['id']==first.json()['id']


def test_unreviewed_stale_missing_candidate_and_ack_are_refused(client,prepared):
    imported(prepared)
    data=client.get(prepared['url'],headers=prepared['owner']).json()
    assert request(client,prepared,data).status_code==409
    data=review(client,prepared)
    assert request(client,prepared,data,number=5).status_code==422
    assert request(client,prepared,data,ack=False).status_code==422
    assert request(client,prepared,{**data,'revision':'0'*64}).status_code==409
    foreign={**prepared,'owner':prepared['other']}
    assert request(client,foreign,data).status_code==404
    assert client.post(prepared['url']+'/previews',json={}).status_code==401


def test_preview_capacity_nested_render_and_deleted_key_checks(client,prepared):
    data=review(client,prepared);key=str(uuid.uuid4())
    first=request(client,prepared,data,key=key).json()
    child={**prepared,'url':f"/api/v1/jobs/{first['id']}/analysis"}
    assert request(client,child,data).status_code==409
    assert request(client,prepared,data).status_code==202
    assert request(client,prepared,data).status_code==429  # Parent + two previews fill owner slots.
    assert client.delete('/api/v1/jobs/'+first['id'],headers=prepared['owner']).status_code==202
    assert request(client,prepared,data,key=key).status_code==410
    assert client.get('/api/v1/jobs/'+prepared['jid'],headers=prepared['owner']).status_code==200


def test_source_delete_tombstones_children_and_preserves_writer_deadline(client,prepared):
    data=review(client,prepared);child=request(client,prepared,data).json()['id']
    deadline=utcnow()+timedelta(minutes=10)
    with SessionLocal.begin() as db:
        row=db.get(RenderJob,child);row.status='processing';row.claim_token=str(uuid.uuid4())
        row.claim_deadline_at=deadline;row.lease_expires_at=deadline
        db.add(RenderAttempt(id=row.claim_token,job_id=child,number=1,status='running',
                             started_at=utcnow(),deadline_at=deadline))
    assert client.delete('/api/v1/jobs/'+prepared['jid'],headers=prepared['owner']).status_code==202
    for identity in (child,prepared['jid']):
        assert client.get('/api/v1/jobs/'+identity,headers=prepared['owner']).status_code==404
        assert client.get('/api/v1/jobs/'+identity+'/download',headers=prepared['owner']).status_code==404
        with SessionLocal() as db:
            row=db.get(RenderJob,identity)
            assert row.status=='deleted' and row.preview_spec_json is None
            assert row.cleanup_after.replace(tzinfo=deadline.tzinfo)>=deadline


def test_parent_restore_tombstone_also_erases_preview(client,prepared):
    from app.restore_replay import apply_records
    data=review(client,prepared);child=request(client,prepared,data).json()['id']
    with SessionLocal.begin() as db:
        apply_records(db,[dict(kind='project_delete',owner=prepared['uid'],project=prepared['jid'],backend='local',namespace=None)])
        assert db.get(RenderJob,child).status=='deleted'
        assert db.get(RenderJob,child).preview_spec_json is None


@pytest.fixture
def actual(client,monkeypatch,tmp_path):
    """Actual media, original synthetic tone; manual text is not ASR evidence."""
    from app.media import probe_video
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-n','-f','lavfi','-i',
        'testsrc2=size=160x90:rate=15','-f','lavfi','-i',
        r'aevalsrc=sin(2*PI*if(lt(t\,1)\,440\,880)*t):s=16000','-t','7',
        '-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True,timeout=30)
    owner={'Authorization':'Bearer '+new_user(client)}
    uid=client.get('/api/v1/me',headers=owner).json()['id']
    monkeypatch.setattr(get_settings(),'english_review_enabled',True)
    monkeypatch.setattr(get_settings(),'english_review_user_ids',(uid,))
    monkeypatch.setattr('app.worker.stop',False)
    payload=source.read_bytes();session=create(client,owner,total=len(payload)).json()['id']
    assert put(client,owner,session,0,payload).status_code==200
    response=client.post(f'/api/v1/upload-sessions/{session}/complete',headers=owner)
    assert response.status_code==200,response.text
    jid=response.json()['id']
    transcript=Transcript(source_sha256=hashlib.sha256(payload).hexdigest(),
        source_duration_ms=math.ceil(probe_video(source)['duration']*1000),language='en',
        provider='manual',timestamp_quality='operator_supplied',words=(
            dict(text='Original',start_ms=1010,end_ms=3500,confidence=.9),
            dict(text='speech.',start_ms=3500,end_ms=6010,confidence=.9)))
    with SessionLocal.begin() as db:
        # Cancel the ordinary baseline so this fixture exercises only its preview.
        db.get(RenderJob,jid).status='cancelled'
        import_transcript(db,owner=uid,job_id=jid,transcript=transcript)
    url=f'/api/v1/jobs/{jid}/analysis'
    initial=client.get(url,headers=owner).json()
    review_data=dict(schema_version='transcript-review-1',source_sha256=transcript.source_sha256,
        transcript_sha256=fingerprint(transcript),acknowledged_original_recording=True,
        sentence_end_words=[2],confirmed_low_confidence_words=[])
    response=client.put(url+'/review',headers=owner,json=dict(revision=initial['revision'],review=review_data))
    assert response.status_code==200,response.text
    return dict(owner=owner,uid=uid,jid=jid,url=url,transcript=transcript,data=response.json(),source=source)


def test_actual_queued_render_download_and_source_preservation(client,actual,tmp_path):
    from app.worker import claim_job,process
    from app.excerpt_render import output_frames
    from app.media import probe_video
    response=request(client,actual,actual['data']);assert response.status_code==202,response.text
    jid=response.json()['id'];claimed=claim_job();assert claimed['id']==jid
    process(claimed)
    row=client.get('/api/v1/jobs/'+jid,headers=actual['owner']).json()
    assert row['status']=='succeeded',row
    assert row['output_duration_seconds']==pytest.approx(5,abs=.034)
    downloaded=client.get('/api/v1/jobs/'+jid+'/download',headers=actual['owner'])
    assert downloaded.status_code==200
    output=tmp_path/'result.mp4';output.write_bytes(downloaded.content)
    assert output_frames(output)==150 and probe_video(output)['width']==1080
    assert hashlib.sha256(actual['source'].read_bytes()).hexdigest()==actual['transcript'].source_sha256
    with SessionLocal() as db:
        child=db.get(RenderJob,jid);snapshot=Path(child.output_path).parent/'input.media'
        assert not snapshot.exists()
    assert client.delete('/api/v1/jobs/'+jid,headers=actual['owner']).status_code==202
    assert client.get('/api/v1/jobs/'+actual['jid'],headers=actual['owner']).status_code==200


def test_source_checksum_failure_cannot_publish_preview(client,actual):
    from app.worker import claim_job,process
    response=request(client,actual,actual['data']);jid=response.json()['id']
    with SessionLocal() as db:source=Path(db.get(RenderJob,actual['jid']).source_path)
    source.write_bytes(b'changed source')
    process(claim_job())
    with SessionLocal() as db:
        child=db.get(RenderJob,jid)
        assert child.status=='failed' and child.error_code=='RENDER_FAILED' and child.output_path is None


def test_source_delete_during_render_cancels_and_fences_output(client,actual,monkeypatch):
    from app.worker import claim_job,process
    from app.media import MediaCancelled
    jid=request(client,actual,actual['data']).json()['id']
    def deleted(*args,**kwargs):
        assert client.delete('/api/v1/jobs/'+actual['jid'],headers=actual['owner']).status_code==202
        assert kwargs['should_cancel']()
        raise MediaCancelled('Source deleted')
    monkeypatch.setattr('app.worker.render_baseline',lambda *a,**k:None)
    monkeypatch.setattr('app.excerpt_render.render_excerpt',deleted)
    process(claim_job())
    with SessionLocal() as db:
        assert db.get(RenderJob,jid).status=='deleted'
        assert db.get(RenderJob,jid).output_path is None


def test_cancelled_preview_cannot_finish_or_publish(client,actual):
    from app.worker import claim_job,mark_done,process
    jid=request(client,actual,actual['data']).json()['id']
    claimed=claim_job();assert claimed['id']==jid
    assert client.post('/api/v1/jobs/'+jid+'/cancel',headers=actual['owner']).status_code==200
    assert not mark_done(jid,claimed['claim_token'],output_path='forbidden.mp4',output_duration=5)
    process(claimed)
    with SessionLocal() as db:
        row=db.get(RenderJob,jid);assert row.status=='cancelled' and row.output_path is None


def test_account_delete_erases_preview_specs(client,prepared):
    data=review(client,prepared);jid=request(client,prepared,data).json()['id']
    result=client.post('/api/v1/account/delete',headers=prepared['owner'],json={
        'current_password':'correct horse battery staple','receipt_key':str(uuid.uuid4())})
    assert result.status_code==202
    with SessionLocal() as db:
        assert db.get(RenderJob,jid).status=='deleted' and db.get(RenderJob,jid).preview_spec_json is None


def test_preview_source_deletions_are_journaled_individually(client,prepared,journal):
    data=review(client,prepared);jid=request(client,prepared,data).json()['id']
    before=journal.checkpoint()['count']
    assert client.delete('/api/v1/jobs/'+prepared['jid'],headers=prepared['owner']).status_code==202
    assert journal.checkpoint()['count']==before+2
    with SessionLocal() as db:assert db.get(RenderJob,jid).status=='deleted'


def test_0021_upgrade_keeps_saved_analysis_and_original_output(migration_engine):
    from alembic import command
    from sqlalchemy import text
    from app.migrate import configuration,upgrade_schema
    from app.models import User
    now=utcnow()
    with migration_engine.begin() as connection:
        command.upgrade(configuration(connection),'0021_project_analysis')
        connection.execute(User.__table__.insert().values(id='owner',email='fixture@example.com',password_hash='fixture'))
        connection.execute(RenderJob.__table__.insert().values(id='source',user_id='owner',title='Original',
            style='vlog',desired_seconds=15,source_duration_seconds=12,source_path='input.mp4',
            output_path='original-output.mp4',status='succeeded'))
        connection.execute(ProjectAnalysis.__table__.insert().values(job_id='source',
            transcript_json='{"fixture":"transcript"}',review_json='{"fixture":"human-review"}',
            proposal_json='{"fixture":"proposal"}',revision='a'*64,created_at=now,updated_at=now))
    upgrade_schema(migration_engine)
    with migration_engine.connect() as connection:
        row=connection.execute(text("SELECT output_path,preview_parent_id,preview_spec_json FROM render_jobs WHERE id='source'")).one()
        assert row==('original-output.mp4',None,None)
        assert connection.scalar(text("SELECT review_json FROM project_analyses WHERE job_id='source'"))=='{"fixture":"human-review"}'
