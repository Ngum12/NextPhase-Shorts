from upload_fixtures import RIGHTS_FORM
import io
import uuid
from app.auth import make_password_hash, verify_password
from app.director import fallback_edl, EditDecisionList, Scene, SceneType

def new_user(client):
    email = f"user-{uuid.uuid4()}@example.com"
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": "correct horse battery staple"})
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]

def test_auth_and_ownership(client):
    token = new_user(client)
    other = new_user(client)
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.get("/api/v1/jobs", headers={"Authorization": f"Bearer {other}"}).json() == []
    assert client.get("/api/v1/jobs/some-other-id", headers={"Authorization": f"Bearer {token}"}).status_code == 404

def test_invalid_video_rejected(client):
    token = new_user(client)
    res = client.post("/api/v1/jobs", headers={"Authorization": f"Bearer {token}"},
                      files={"file": ("test.mp4", io.BytesIO(b"This is not a video"), "video/mp4")},
                      data={**RIGHTS_FORM, **({"style": "vlog", "desired_seconds": "30", "title": "Test"})})
    assert res.status_code == 422

def test_style_list_truthfully_marks_planned(client):
    res = client.get("/api/v1/styles")
    assert res.status_code == 200
    assert len(res.json()) == 6
    assert all(not s["available"] for s in res.json())

def test_60_second_hard_limit(client):
    token = new_user(client)
    res = client.post("/api/v1/jobs", headers={"Authorization": f"Bearer {token}"},
                      files={"file": ("clip.mp4", io.BytesIO(b"invalid"), "video/mp4")},
                      data={**RIGHTS_FORM, **({"style": "vlog", "desired_seconds": "61", "title": "Test"})})
    assert res.status_code == 422

def test_password_hash():
    stored = make_password_hash("long enough password")
    assert verify_password("long enough password", stored)
    assert not verify_password("incorrect password", stored)

def test_edl_guardrails():
    plan = fallback_edl("documentary", source_seconds=124.4, requested_seconds=60)
    assert plan.output_seconds == 60
    assert plan.scenes[0].kind == SceneType.TALKING_HEAD
    bad = EditDecisionList("vlog", 61, (Scene(SceneType.TALKING_HEAD, 0, 61),))
    try:
        bad.validate()
    except ValueError:
        pass
    else:
        raise AssertionError("Duration guardrail did not reject 61 second video")


def test_upload_rejection_boundaries(client, monkeypatch):
    from app.main import settings
    from unittest.mock import Mock

    before = set(settings.storage_dir.rglob("input.*"))
    token = new_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    def upload(content=b"test", filename="clip.mp4", **data):
        return client.post("/api/v1/jobs", headers=headers,
                           files={"file": (filename, io.BytesIO(content), "video/mp4")},
                           data={**RIGHTS_FORM, **({"style": "vlog", "desired_seconds": "15", **data})})

    assert upload(b"").status_code == 422
    assert upload(filename="clip.exe").status_code == 415
    assert upload(style="unknown").status_code == 422
    assert upload(title="   ").status_code == 422
    monkeypatch.setattr(settings, "max_upload_bytes", 3)
    assert upload(b"1234").status_code == 413
    monkeypatch.setattr(settings, "max_upload_bytes", 314572800)
    probe = Mock(return_value={"duration": 600.01, "width": 320, "height": 240})
    monkeypatch.setattr("app.main.probe_video", probe)
    assert upload().status_code == 422
    probe.assert_called_once()
    # Every rejected upload must leave no source media behind.
    assert set(settings.storage_dir.rglob("input.*")) == before


def test_login_and_invalid_sessions(client):
    email = f"{uuid.uuid4()}@example.com"
    password = "login-test-password"
    assert client.post('/api/v1/auth/register', json={"email": email, "password": password}).status_code == 201
    response = client.post('/api/v1/auth/login', json={"email": email, "password": password})
    assert response.status_code == 200
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    assert client.get('/api/v1/me', headers=headers).json()['email'] == email
    assert client.post('/api/v1/auth/login', json={"email": email, "password": "wrong"}).status_code == 401
    assert client.get('/api/v1/jobs', headers={"Authorization": "Bearer invalid"}).status_code == 401
