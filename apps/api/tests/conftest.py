"""Test app with an isolated temporary SQLite DB and media directory."""
import os
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="nextphase-test-"))
os.environ["APP_ENV"] = "test"
os.environ["BUDGET_STATE_FILE"] = ""
os.environ["RESTORE_JOURNAL_DIR"] = ""
os.environ["RESTORE_JOURNAL_KEY"] = ""
os.environ["RESTORE_JOURNAL_KEY_FILE"] = ""
# Legacy regressions exercise owner limits; dedicated capacity tests set small global limits.
os.environ['GLOBAL_ACTIVE_LIMIT']='10000'
os.environ['GLOBAL_PROCESSING_LIMIT']='100'
os.environ['GLOBAL_STORAGE_BYTES']='1099511627776'
os.environ['INGRESS_LIMIT']='100'
os.environ['MIN_FREE_DISK_BYTES']='0'
# Isolated tests never read operator-mounted credentials or dotenv file bindings.
for key in ['JWT_SECRET_FILE', 'DATABASE_URL_FILE', 'S3_ACCESS_KEY_ID_FILE', 'S3_SECRET_ACCESS_KEY_FILE', 'QUEUE_PASSWORD_FILE', 'RESEND_API_KEY_FILE', 'AUTH_MAIL_ENCRYPTION_KEYS_FILE']:os.environ[key]=''
os.environ["AUTH_MAIL_BACKEND"] = "disabled"
os.environ['AUTH_MAIL_SEND_ENABLED']='false'
os.environ['AUTH_REQUIRE_VERIFIED_EMAIL']='false'
os.environ['RESEND_API_KEY']=''
os.environ['AUTH_MAIL_ENCRYPTION_KEYS']=''
os.environ['QUEUE_BACKEND']='database'
os.environ['WORKER_REQUIRE_SANDBOX']='false'
os.environ['WORKER_REQUIRE_LIMITS']='false'
os.environ["AUTH_MAIL_DIR"] = str(ROOT / "auth-mail")
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


@pytest.fixture(autouse=True)
def finish_active_fixture_work():
    # Every test owns its synthetic live work. Short real leases must not expire
    # an unrelated earlier test's intentionally unfinished claims during a slow run.
    yield
    from sqlalchemy import update
    from app.db import SessionLocal
    from app.models import RenderJob,RenderAttempt,QueueSignal,UploadSession,utcnow
    with SessionLocal.begin() as db:
        db.execute(update(RenderJob).where(RenderJob.status.in_(('queued','processing')))
            .values(status='cancelled',claim_token=None,lease_expires_at=None,claim_deadline_at=None,next_attempt_at=None))
        db.execute(update(RenderAttempt).where(RenderAttempt.status=='running').values(status='cancelled',finished_at=utcnow()))
        db.execute(update(QueueSignal).values(completed_at=utcnow(),lease_token=None,lease_until=None))
        # Old legacy-inventory fixtures are no longer live after their test; avoid
        # contaminating the next test's shared global inventory gate.
        from sqlalchemy import or_
        for model in (RenderJob,UploadSession):
            db.execute(update(model).where(or_(model.storage_reserved_bytes.is_(None),model.max_render_bytes.is_(None)))
                .values(storage_reserved_bytes=0,max_render_bytes=67108864))


def pytest_sessionfinish(session, exitstatus):
    if pg_admin is not None:
        engine.dispose()
        with pg_admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{pg_schema}" CASCADE')
        pg_admin.dispose()
