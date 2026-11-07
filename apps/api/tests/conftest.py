"""Test app with an isolated temporary SQLite DB and media directory."""
import os
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="nextphase-test-"))
os.environ["APP_ENV"] = "test"
os.environ['MEDIA_BACKEND'] = 'local'
os.environ['DIRECT_UPLOADS_ENABLED'] = 'false'
# Regression suites create many isolated accounts behind one test-client IP.
# Auth-specific tests set small limits explicitly and exercise enforcement.
for key in ('AUTH_LOGIN_ACCOUNT_LIMIT', 'AUTH_LOGIN_IP_LIMIT', 'AUTH_REGISTER_IP_LIMIT', 'AUTH_PASSWORD_LIMIT'):
    os.environ[key] = '10000'
test_database_url = os.getenv("NEXTPHASE_TEST_DATABASE_URL")
pg_admin = pg_schema = None
if test_database_url:
    from sqlalchemy.engine import make_url
    from sqlalchemy import create_engine
    import uuid
    if not (make_url(test_database_url).database or '').endswith('_test'):
        raise RuntimeError('Integration database name must end with _test; use a disposable database.')
    # Each pytest process gets fresh synthetic metadata. Reusing a test DB must
    # not make old mock-store tombstones interfere with cleanup-priority tests.
    pg_schema = 'pytest_' + uuid.uuid4().hex
    pg_admin = create_engine(test_database_url)
    with pg_admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{pg_schema}"')
    url = make_url(test_database_url)
    test_database_url = url.set(query={**url.query, 'options': '-csearch_path='+pg_schema}).render_as_string(hide_password=False)
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


def pytest_sessionfinish(session, exitstatus):
    if pg_admin is not None:
        engine.dispose()
        with pg_admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{pg_schema}" CASCADE')
        pg_admin.dispose()
