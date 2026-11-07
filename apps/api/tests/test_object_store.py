"""Fault tests complement the real local-S3 HTTP smoke, not an S3 emulator."""
import hashlib
import io
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import pytest
from botocore.response import StreamingBody
from botocore.exceptions import ClientError
from app import object_store as store
from app.config import get_settings, Settings
from app.db import SessionLocal
from app.models import RenderJob, utcnow
from app.worker import claim_job, process
from test_api import new_user
from test_upload_sessions import context, create, fill
from upload_fixtures import RIGHTS_FORM


class MemoryS3:
    def __init__(self):
        self.objects = {}; self.fail_put = False; self.fail_delete = False; self.versioned = False
    def put_object(self, **args):
        if self.fail_put: raise ClientError({'Error': {'Code': 'AccessDenied'}}, 'PutObject')
        self.objects[args['Key']] = (args['Body'].read(), args['Metadata'])
    def head_object(self, **args):
        if args['Key'] not in self.objects: raise ClientError({'Error': {'Code': 'NoSuchKey'}}, 'HeadObject')
        data, metadata = self.objects[args['Key']]
        return {'ContentLength': len(data), 'Metadata': metadata}
    def get_object(self, **args):
        data, _ = self.objects[args['Key']]
        return {**self.head_object(**args), 'Body': StreamingBody(io.BytesIO(data), len(data))}
    def list_objects_v2(self, **args):
        return {'Contents': [{'Key': key} for key in self.objects if key.startswith(args['Prefix'])][:args['MaxKeys']]}
    def delete_objects(self, **args):
        if self.fail_delete: return {'Errors': [{'Code': 'AccessDenied'}]}
        for item in args['Delete']['Objects']: self.objects.pop(item['Key'], None)
        return {}
    def get_bucket_versioning(self, **args): return {'Status': 'Enabled'} if self.versioned else {}


@pytest.fixture
def remote(monkeypatch):
    settings = get_settings(); fake = MemoryS3()
    for name, value in {'media_backend':'s3', 's3_bucket':'nextphase-test',
                        's3_endpoint':'http://127.0.0.1:8333', 's3_public_endpoint':'http://127.0.0.1:8333',
                        's3_access_key':'test-only-access', 's3_secret_key':'test-only-secret'}.items():
        monkeypatch.setattr(settings, name, value)
    actual_client = store.client
    monkeypatch.setattr(store, 'client', lambda public=False: actual_client(True) if public else fake)
    actual_client.cache_clear()
    yield fake
    actual_client.cache_clear()


def post(client, owner):
    return client.post('/api/v1/jobs', headers=owner, data=RIGHTS_FORM,
                       files={'file': ('source.mp4', b'private-source', 'video/mp4')})


def fake_render(source, output, duration, **kwargs):
    assert source.read_bytes() == b'private-source'
    output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(b'private-result')
    return {'duration': 2}


def test_remote_legacy_render_download_and_scoped_signed_link(client, monkeypatch, remote):
    monkeypatch.setattr('app.main.probe_video', lambda _: {'duration':2})
    monkeypatch.setattr('app.worker.render_baseline', fake_render)
    owner = {'Authorization':'Bearer '+new_user(client)}
    other = {'Authorization':'Bearer '+new_user(client)}
    result = post(client, owner); assert result.status_code == 201
    jid = result.json()['id']
    with SessionLocal() as db:
        row = db.get(RenderJob, jid); uid = row.user_id
        assert row.media_backend == 's3' and row.source_path.startswith('s3://')
        assert not (get_settings().storage_dir/uid/jid/'input.mp4').exists()
    claimed = claim_job(); assert claimed['id'] == jid; process(claimed)
    download = client.get(f'/api/v1/jobs/{jid}/download', headers=owner)
    assert download.status_code == 200 and download.content == b'private-result'
    assert download.headers['cache-control'] == 'private, no-store' and not download.history
    assert client.post(f'/api/v1/jobs/{jid}/download-link', headers=other).status_code == 404
    assert client.post(f'/api/v1/jobs/{jid}/download-link').status_code == 401
    link = client.post(f'/api/v1/jobs/{jid}/download-link', headers=owner)
    assert link.status_code == 200 and link.json()['expires_in_seconds'] == 60
    query = parse_qs(urlsplit(link.json()['url']).query)
    assert query['X-Amz-Expires'] == ['60'] and query['X-Amz-Algorithm'] == ['AWS4-HMAC-SHA256']
    assert 'private-source' not in link.text and owner['Authorization'] not in link.text
    assert not list((get_settings().storage_dir/uid/jid).rglob('input.media'))
    assert not list((get_settings().storage_dir/uid/jid).rglob('output.mp4'))
    from app.deletion import cleanup_deleted
    remote.fail_delete = True
    assert client.delete(f'/api/v1/jobs/{jid}', headers=owner).status_code == 202
    assert client.post(f'/api/v1/jobs/{jid}/download-link', headers=owner).status_code == 404
    assert client.get(f'/api/v1/jobs/{jid}/download', headers=owner).status_code == 404
    previous_endpoint = get_settings().s3_endpoint
    remote.fail_delete = False
    monkeypatch.setattr(get_settings(), 's3_endpoint', 'http://localhost:8333')
    cleanup_deleted()
    with SessionLocal() as db: assert db.get(RenderJob, jid).media_deleted_at is None
    assert remote.objects
    monkeypatch.setattr(get_settings(), 's3_endpoint', previous_endpoint)
    remote.fail_delete = True
    cleanup_deleted()
    with SessionLocal() as db: assert db.get(RenderJob, jid).media_deleted_at is None
    remote.fail_delete = False; cleanup_deleted()
    with SessionLocal() as db: assert db.get(RenderJob, jid).media_deleted_at is not None
    assert not remote.objects


def test_failed_remote_admission_keeps_resumable_progress(client, context, remote):
    owner, _, _ = context; session = create(client, owner, total=24).json(); sid = session['id']
    fill(client, owner, sid, b'abcdefghijklmnopqrstuvwx')
    remote.fail_put = True
    assert client.post(f'/api/v1/upload-sessions/{sid}/complete', headers=owner).status_code == 503
    state = client.get(f'/api/v1/upload-sessions/{sid}', headers=owner).json()
    assert state['received_bytes'] == 24 and state['status'] == 'uploading'
    remote.fail_put = False
    first = client.post(f'/api/v1/upload-sessions/{sid}/complete', headers=owner)
    second = client.post(f'/api/v1/upload-sessions/{sid}/complete', headers=owner)
    assert first.status_code == second.status_code == 200 and first.json()['id'] == second.json()['id']
    with SessionLocal.begin() as db:
        row = db.get(RenderJob, first.json()['id']); assert row.media_backend == 's3'; row.status = 'cancelled'
    assert len(remote.objects) == 1


def test_remote_failure_never_publishes_success(client, monkeypatch, remote):
    monkeypatch.setattr('app.main.probe_video', lambda _: {'duration':2})
    monkeypatch.setattr('app.worker.render_baseline', fake_render)
    owner = {'Authorization':'Bearer '+new_user(client)}
    jid = post(client, owner).json()['id']; job = claim_job(); assert job['id'] == jid
    remote.fail_put = True; process(job)
    with SessionLocal() as db:
        row = db.get(RenderJob, jid)
        assert row.status == 'failed' and row.error_code == 'STORAGE_UNAVAILABLE' and row.output_path is None


def test_remote_source_integrity_and_byte_bound(tmp_path, remote):
    uid, jid = str(uuid.uuid4()), str(uuid.uuid4()); path = tmp_path/'original'; path.write_bytes(b'known-source')
    key = store.source_key(uid, jid, '.mp4'); ref = store.put(path, key, 1024)
    data, metadata = remote.objects[key]; remote.objects[key] = (b'wrong-source', metadata)
    with pytest.raises(store.ObjectStoreError): store.fetch(ref, key, tmp_path/'bad', 1024)
    assert not (tmp_path/'bad').exists()
    with pytest.raises(store.ObjectStoreError): store.open_object(ref, key, 2)
    with pytest.raises(store.ObjectStoreError): store.parse_reference(ref, store.source_key(uid,str(uuid.uuid4()),'.mp4'))
    with pytest.raises(ValueError): store.prefix(uid, '../escape')


def test_remote_cleanup_never_touches_other_project_and_refuses_versioning(tmp_path, remote):
    uid, jid, other = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    path = tmp_path/'source'; path.write_bytes(b'original')
    store.put(path, store.source_key(uid,jid,'.mp4'),1024)
    keep = store.source_key(uid,other,'.mp4'); store.put(path,keep,1024)
    remote.versioned = True
    with pytest.raises(store.ObjectStoreError): store.remove_project(uid,jid)
    assert len(remote.objects) == 2
    remote.versioned = False; store.remove_project(uid,jid)
    assert set(remote.objects) == {keep}


@pytest.mark.parametrize('endpoint', ['http://example.org', 'https://user:password@example.org',
    'https://example.org/private', 'file:///etc/passwd', 'https://example.org?token=secret'])
def test_remote_config_rejects_unsafe_endpoints(monkeypatch, endpoint):
    monkeypatch.setenv('MEDIA_BACKEND','s3'); monkeypatch.setenv('S3_ENDPOINT',endpoint)
    monkeypatch.setenv('S3_BUCKET','nextphase-test');monkeypatch.setenv('S3_ACCESS_KEY_ID','test-only')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY','test-only')
    with pytest.raises(RuntimeError): Settings()


def test_cancel_during_remote_publication_keeps_fence(client, monkeypatch, remote):
    monkeypatch.setattr('app.main.probe_video', lambda _: {'duration':2})
    monkeypatch.setattr('app.worker.render_baseline', fake_render)
    owner = {'Authorization':'Bearer '+new_user(client)}
    jid = post(client, owner).json()['id']; job = claim_job(); assert job['id'] == jid
    original = remote.put_object
    def racing_put(**args):
        original(**args)
        if args['Key'].endswith('/output.mp4'):
            with SessionLocal.begin() as db:
                row = db.get(RenderJob,jid); row.status='cancelled';row.claim_token=None;row.lease_expires_at=None
    remote.put_object = racing_put
    process(job)
    with SessionLocal() as db:
        row = db.get(RenderJob,jid);assert row.status=='cancelled' and row.output_path is None
    assert client.get(f'/api/v1/jobs/{jid}/download',headers=owner).status_code==409
    from app.deletion import cleanup_deleted
    client.delete(f'/api/v1/jobs/{jid}',headers=owner);cleanup_deleted()
    assert not remote.objects


def test_legacy_local_success_remains_readable_in_remote_mode(client, monkeypatch, remote):
    monkeypatch.setattr('app.main.probe_video', lambda _: {'duration':2})
    owner = {'Authorization':'Bearer '+new_user(client)}
    jid = post(client,owner).json()['id']
    with SessionLocal.begin() as db:
        row=db.get(RenderJob,jid);path=get_settings().storage_dir/row.user_id/jid/'output.mp4'
        path.write_bytes(b'legacy-local');row.media_backend='local';row.status='succeeded';row.output_path=str(path)
    assert client.get(f'/api/v1/jobs/{jid}/download',headers=owner).content==b'legacy-local'
    assert client.post(f'/api/v1/jobs/{jid}/download-link',headers=owner).status_code==409


def test_local_inventory_never_guesses_remote_usage(client, monkeypatch, remote):
    monkeypatch.setattr('app.main.probe_video', lambda _: {'duration':2})
    owner={'Authorization':'Bearer '+new_user(client)};jid=post(client,owner).json()['id']
    with SessionLocal.begin() as db:
        row=db.get(RenderJob,jid);row.storage_reserved_bytes=None;row.status='cancelled'
    from app.storage import reconcile
    _,missing=reconcile();assert missing>=1
    with SessionLocal() as db:assert db.get(RenderJob,jid).storage_reserved_bytes is None
    assert client.get('/api/v1/me/storage',headers=owner).json()['available_bytes'] is None
    client.delete(f'/api/v1/jobs/{jid}',headers=owner)
    from app.deletion import cleanup_deleted
    cleanup_deleted()
