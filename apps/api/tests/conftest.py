"""Test app with an isolated temporary SQLite DB and media directory."""
import os
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="nextphase-test-"))
os.environ["APP_ENV"] = "test"
# Regression suites create many isolated accounts behind one test-client IP.
# Auth-specific tests set small limits explicitly and exercise enforcement.
for key in ('AUTH_LOGIN_ACCOUNT_LIMIT', 'AUTH_LOGIN_IP_LIMIT', 'AUTH_REGISTER_IP_LIMIT', 'AUTH_PASSWORD_LIMIT'):
    os.environ[key] = '10000'
test_database_url = os.getenv("NEXTPHASE_TEST_DATABASE_URL")
if test_database_url:
    from sqlalchemy.engine import make_url
    if not (make_url(test_database_url).database or '').endswith('_test'):
        raise RuntimeError('Integration database name must end with _test; use a disposable database.')
os.environ["DATABASE_URL"] = test_database_url or "sqlite:///" + str(ROOT / "test.sqlite3")
os.environ["STORAGE_DIR"] = str(ROOT / "media")
os.environ["JWT_SECRET"] = "unit-test-private-key-unique-long-secret-12345"

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine
from app.migrate import upgrade_schema

upgrade_schema(engine)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
