import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from app.migrate import upgrade_schema, require_current_schema
from app.migrations.baseline import metadata
from app.db import Base
from app import models  # register current metadata


@pytest.fixture
def migration_engine(tmp_path):
    import os
    import uuid
    url = os.getenv('NEXTPHASE_TEST_DATABASE_URL')
    if not url:
        engine = sa.create_engine('sqlite:///' + str(tmp_path / 'migration.db'))
        yield engine
        engine.dispose()
        return
    # Isolate each PostgreSQL migration test from the application's test tables.
    schema = 'migration_' + uuid.uuid4().hex
    admin = sa.create_engine(url)
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = sa.create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()


def test_fresh_upgrade_is_repeatable_and_matches_models(migration_engine):
    engine = migration_engine
    with pytest.raises(RuntimeError, match='not current'):
        require_current_schema(engine)
    assert sa.inspect(engine).get_table_names() == []
    upgrade_schema(engine)
    upgrade_schema(engine)
    require_current_schema(engine)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    engine.dispose()


def test_legacy_adoption_preserves_users_and_completed_jobs(migration_engine):
    engine = migration_engine
    baseline = metadata()
    baseline.create_all(engine)
    with engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO users VALUES ('owner', 'owner@example.com', 'hash', CURRENT_TIMESTAMP)"))
        connection.execute(sa.text("""INSERT INTO render_jobs
            (id,user_id,title,style,desired_seconds,source_duration_seconds,source_path,output_path,
             status,attempt_count,created_at) VALUES
            ('completed','owner','Keep me','vlog',15,5,'source','legacy/output.mp4','succeeded',1,CURRENT_TIMESTAMP),
            ('interrupted','owner','Retry me','vlog',15,5,'source',NULL,'processing',1,CURRENT_TIMESTAMP),
            ('exhausted','owner','Fail me','vlog',15,5,'source',NULL,'processing',2,CURRENT_TIMESTAMP)"""))
    with pytest.raises(RuntimeError, match='Unversioned'):
        upgrade_schema(engine)
    upgrade_schema(engine, adopt_legacy=True)
    upgrade_schema(engine, adopt_legacy=True)
    require_current_schema(engine)
    with engine.connect() as connection:
        assert connection.scalar(sa.text('SELECT count(*) FROM users')) == 1
        rows = {row.id: row for row in connection.execute(sa.text('SELECT * FROM render_jobs'))}
        assert rows['completed'].output_path == 'legacy/output.mp4'
        assert rows['completed'].status == 'succeeded'
        assert rows['interrupted'].status == 'queued'
        assert rows['exhausted'].error_code == 'MAX_RETRIES'
    engine.dispose()


def test_unknown_legacy_schema_is_not_adopted(migration_engine):
    engine = migration_engine
    with engine.begin() as connection:
        connection.execute(sa.text('CREATE TABLE important (id INTEGER PRIMARY KEY)'))
        connection.execute(sa.text('INSERT INTO important VALUES (42)'))
    with pytest.raises(RuntimeError, match='differs'):
        upgrade_schema(engine, adopt_legacy=True)
    with engine.connect() as connection:
        assert connection.scalar(sa.text('SELECT id FROM important')) == 42
        assert sa.inspect(connection).get_table_names() == ['important']
    engine.dispose()


def test_outdated_revision_requires_explicit_upgrade(migration_engine):
    from alembic import command
    from app.migrate import configuration
    with migration_engine.begin() as connection:
        command.upgrade(configuration(connection), '0001_baseline')
    with pytest.raises(RuntimeError, match='not current'):
        require_current_schema(migration_engine)
    upgrade_schema(migration_engine)
    require_current_schema(migration_engine)


def test_staging_rejects_sqlite(monkeypatch, tmp_path):
    from app.config import Settings
    monkeypatch.setenv('APP_ENV', 'staging')
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'no-staging.db'))
    with pytest.raises(RuntimeError, match='PostgreSQL'):
        Settings()


def test_auth_upgrade_preserves_pending_uploads_and_completed_jobs(migration_engine):
    from alembic import command
    from app.migrate import configuration
    from app.models import User, RenderJob, UploadSession, UploadPart, utcnow
    from datetime import timedelta
    with migration_engine.begin() as connection:
        command.upgrade(configuration(connection), '0004_upload_sessions')
        connection.execute(User.__table__.insert().values(id='owner',email='keep@example.com',password_hash='unchanged'))
        connection.execute(RenderJob.__table__.insert().values(id='done',user_id='owner',title='Keep',style='vlog',
            desired_seconds=15,source_duration_seconds=5,source_path='old/source.mp4',output_path='old/output.mp4',status='succeeded'))
        connection.execute(UploadSession.__table__.insert().values(id='pending',user_id='owner',client_key='same-key',
            descriptor_hash='a'*64,file_name='source.mp4',extension='.mp4',title='Keep upload',style='vlog',
            desired_seconds=15,total_bytes=2000000,received_bytes=1048576,chunk_bytes=1048576,expires_at=utcnow()+timedelta(hours=1)))
        connection.execute(UploadPart.__table__.insert().values(session_id='pending',offset=0,size=1048576,sha256='b'*64))
    upgrade_schema(migration_engine)
    upgrade_schema(migration_engine)
    with migration_engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT password_hash FROM users WHERE id='owner'"))=='unchanged'
        assert connection.scalar(sa.text("SELECT output_path FROM render_jobs WHERE id='done'"))=='old/output.mp4'
        assert connection.scalar(sa.text("SELECT received_bytes FROM upload_sessions WHERE id='pending'"))==1048576
        assert connection.scalar(sa.text("SELECT count(*) FROM upload_parts"))==1
        assert connection.scalar(sa.text("SELECT count(*) FROM auth_sessions"))==0


def test_attempt_migration_preserves_auth_session(migration_engine):
    from alembic import command
    from app.migrate import configuration
    from app.models import AuthSession, User, utcnow
    from datetime import timedelta
    with migration_engine.begin() as connection:
        command.upgrade(configuration(connection),'0005_auth_sessions')
        connection.execute(User.__table__.insert().values(id='retained',email='retained@example.com',password_hash='hash'))
        connection.execute(AuthSession.__table__.insert().values(id='c'*64,user_id='retained',
            created_at=utcnow(),expires_at=utcnow()+timedelta(hours=1)))
    upgrade_schema(migration_engine)
    with migration_engine.connect() as connection:
        assert connection.scalar(sa.text('SELECT count(*) FROM auth_sessions'))==1
        assert connection.scalar(sa.text('SELECT count(*) FROM render_attempts'))==0
