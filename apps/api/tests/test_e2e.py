from upload_fixtures import RIGHTS_FORM
import io
import shutil
import subprocess
import uuid
from pathlib import Path
import pytest
from app.media import probe_video
from app.worker import claim_job, process

@pytest.mark.skipif(shutil.which('ffmpeg') is None, reason='ffmpeg unavailable')
def test_upload_worker_download_owner_only(client, tmp_path: Path):
    email1 = f'{uuid.uuid4()}@example.com'
    email2 = f'{uuid.uuid4()}@example.com'
    def register(email):
        r = client.post('/api/v1/auth/register', json={'email':email,'password':'example-password-123'})
        assert r.status_code == 201
        return {'Authorization':'Bearer '+r.json()['access_token']}
    own = register(email1)
    other = register(email2)
    clip = tmp_path / 'source.mp4'
    subprocess.run(['ffmpeg', '-nostdin','-loglevel','error', '-y', '-f','lavfi',
                    '-i','color=c=navy:s=320x240:r=15', '-t','1.5',
                    '-c:v','libx264','-pix_fmt','yuv420p',str(clip)],check=True,timeout=30)
    response = client.post('/api/v1/jobs', headers=own,
                           files={'file':('sample.mp4',io.BytesIO(clip.read_bytes()),'video/mp4')},
                           data={**RIGHTS_FORM, **({'style':'documentary','desired_seconds':'15','title':'Pilot test'})})
    assert response.status_code == 201, response.text
    job_id = response.json()['id']
    assert response.json()['status']=='queued'
    assert client.get(f'/api/v1/jobs/{job_id}',headers=other).status_code==404
    assert client.get(f'/api/v1/jobs/{job_id}/download',headers=other).status_code==404
    job = claim_job()
    assert job and job['id']==job_id
    process(job)
    result = client.get(f'/api/v1/jobs/{job_id}',headers=own)
    assert result.json()['status']=='succeeded',result.text
    downloaded = client.get(f'/api/v1/jobs/{job_id}/download',headers=own)
    assert downloaded.status_code==200
    assert downloaded.headers['content-type'].startswith('video/mp4')
    out = tmp_path/'check.mp4'
    out.write_bytes(downloaded.content)
    metadata = probe_video(out)
    assert metadata['width']==1080 and metadata['height']==1920
    assert metadata['duration'] <= 60.0
