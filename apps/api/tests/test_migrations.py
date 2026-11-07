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


def test_deletion_migration_keeps_existing_job_visible(migration_engine):
    from alembic import command
    from app.migrate import configuration
    from app.models import User, RenderJob
    with migration_engine.begin() as connection:
        command.upgrade(configuration(connection),'0006_render_attempts')
        connection.execute(User.__table__.insert().values(id='keep-owner',email='keep-owner@example.com',password_hash='hash'))
        connection.execute(RenderJob.__table__.insert().values(id='keep-job',user_id='keep-owner',title='Keep this',style='vlog',
            desired_seconds=15,source_duration_seconds=5,source_path='old/input.mp4',output_path='old/output.mp4',status='succeeded'))
    upgrade_schema(migration_engine)
    upgrade_schema(migration_engine)
    with migration_engine.connect() as connection:
        row=connection.execute(sa.text("SELECT status,title,output_path,deleted_at,cleanup_after FROM render_jobs WHERE id='keep-job'")).one()
        assert row.status=='succeeded' and row.title=='Keep this' and row.output_path=='old/output.mp4'
        assert row.deleted_at is None and row.cleanup_after is None


def test_storage_migration_does_not_guess_historical_usage(migration_engine):
    from alembic import command
    from app.migrate import configuration
    from app.models import User,RenderJob
    with migration_engine.begin() as connection:
        command.upgrade(configuration(connection),'0007_project_deletion')
        connection.execute(User.__table__.insert().values(id='inventory-owner',email='inventory@example.com',password_hash='unchanged'))
        connection.execute(RenderJob.__table__.insert().values(id='inventory-job',user_id='inventory-owner',title='Keep video',style='vlog',
            desired_seconds=15,source_duration_seconds=5,source_path='input.mp4',status='queued'))
    upgrade_schema(migration_engine)
    with migration_engine.connect() as connection:
        row=connection.execute(sa.text("SELECT title,status,storage_reserved_bytes,max_render_bytes FROM render_jobs WHERE id='inventory-job'")).one()
        assert row.title=='Keep video' and row.status=='queued'
        assert row.storage_reserved_bytes is None and row.max_render_bytes is None


def test_rights_migration_preserves_old_rows_without_fabricating_ack(migration_engine):
    from alembic import command
    from app.migrate import configuration
    from app.models import User,RenderJob,UploadSession,utcnow
    from datetime import timedelta
    with migration_engine.begin() as connection:
        command.upgrade(configuration(connection),'0008_storage_budgets')
        connection.execute(User.__table__.insert().values(id='old-rights-owner',email='old-rights@example.com',password_hash='hash'))
        connection.execute(RenderJob.__table__.insert().values(id='old-rights-job',user_id='old-rights-owner',title='Keep',style='vlog',
            desired_seconds=15,source_duration_seconds=5,source_path='input.mp4',status='succeeded'))
        connection.execute(UploadSession.__table__.insert().values(id='old-rights-session',user_id='old-rights-owner',client_key='keep-key',
            descriptor_hash='a'*64,file_name='source.mp4',extension='.mp4',title='Keep',style='vlog',desired_seconds=15,
            total_bytes=24,received_bytes=8,chunk_bytes=8,expires_at=utcnow()+timedelta(hours=1)))
    upgrade_schema(migration_engine)
    with migration_engine.connect() as connection:
        for table in ('render_jobs','upload_sessions'):
            row=connection.execute(sa.text(f'SELECT rights_version,rights_confirmed_at FROM {table}')).one()
            assert row.rights_version is None and row.rights_confirmed_at is None
        assert connection.scalar(sa.text('SELECT received_bytes FROM upload_sessions'))==8


def test_object_backend_migration_keeps_old_media_local(migration_engine):
    from alembic import command
    from app.migrate import configuration
    with migration_engine.begin() as connection:
        command.upgrade(configuration(connection), '0009_upload_rights')
        connection.execute(sa.text("INSERT INTO users VALUES ('object-owner','object-owner@example.com','hash',CURRENT_TIMESTAMP)"))
        connection.execute(sa.text("""INSERT INTO render_jobs
            (id,user_id,title,style,desired_seconds,source_duration_seconds,source_path,output_path,status,attempt_count,created_at)
            VALUES ('object-job','object-owner','Keep','vlog',15,5,'old/input.mp4','old/output.mp4','succeeded',1,CURRENT_TIMESTAMP)"""))
    upgrade_schema(migration_engine); upgrade_schema(migration_engine)
    with migration_engine.connect() as connection:
        row = connection.execute(sa.text("SELECT media_backend,source_path,output_path,status FROM render_jobs WHERE id='object-job'")).one()
        assert row.media_backend == 'local' and row.source_path == 'old/input.mp4'
        assert row.output_path == 'old/output.mp4' and row.status == 'succeeded'


def test_direct_upload_migration_preserves_api_session_and_parts(migration_engine):
    from alembic import command
    from app.migrate import configuration
    from app.models import User,UploadSession,UploadPart,utcnow
    from datetime import timedelta
    with migration_engine.begin() as connection:
        command.upgrade(configuration(connection),'0010_object_backend')
        connection.execute(User.__table__.insert().values(id='direct-old-owner',email='direct-old@example.com',password_hash='hash'))
        connection.execute(UploadSession.__table__.insert().values(id='direct-old-session',user_id='direct-old-owner',client_key='keep-direct-key',
            descriptor_hash='a'*64,file_name='source.mp4',extension='.mp4',title='Keep',style='vlog',desired_seconds=15,
            total_bytes=24,received_bytes=8,chunk_bytes=8,expires_at=utcnow()+timedelta(hours=1)))
        connection.execute(UploadPart.__table__.insert().values(session_id='direct-old-session',offset=0,size=8,sha256='b'*64))
    upgrade_schema(migration_engine);upgrade_schema(migration_engine)
    with migration_engine.connect() as connection:
        row=connection.execute(sa.text("SELECT transfer_backend,received_bytes,object_store_id FROM upload_sessions")).one()
        assert row.transfer_backend=='api' and row.received_bytes==8 and row.object_store_id is None
        row=connection.execute(sa.text('SELECT sha256,object_reference,direct_grant_id FROM upload_parts')).one()
        assert row.sha256=='b'*64 and row.object_reference is None and row.direct_grant_id is None
        assert connection.scalar(sa.text('SELECT count(*) FROM direct_upload_grants'))==0
