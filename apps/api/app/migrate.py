"""Explicit schema upgrades; application startup never modifies schema."""
import argparse
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect


def configuration(connection):
    config = Config()
    config.set_main_option('script_location', str(Path(__file__).parent / 'migrations'))
    config.attributes['connection'] = connection
    return config


def upgrade_schema(engine, *, adopt_legacy=False):
    # One explicit migration process, while all API/worker processes are stopped.
    with engine.begin() as connection:
        config = configuration(connection)
        context = MigrationContext.configure(connection)
        if not context.get_current_heads() and inspect(connection).get_table_names():
            if not adopt_legacy:
                raise RuntimeError('Unversioned database: back up and stop services, then run python -m app.migrate --adopt-legacy.')
            from .migrations.baseline import metadata
            differences = compare_metadata(context, metadata())
            if differences:
                raise RuntimeError('Legacy schema differs from Stage 1; refusing to stamp or alter it. Review schema manually.')
            command.stamp(config, '0001_baseline')
        command.upgrade(config, 'head')


def require_current_schema(engine):
    with engine.connect() as connection:
        config = configuration(connection)
        expected = set(ScriptDirectory.from_config(config).get_heads())
        actual = set(MigrationContext.configure(connection).get_current_heads())
        if actual != expected:
            raise RuntimeError('Database schema is not current. Stop services, back up, and run python -m app.migrate before starting.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adopt-legacy', action='store_true', help='Validate and adopt the original unversioned Stage 1 schema after backup; stop all services first.')
    args = parser.parse_args()
    from .db import engine
    upgrade_schema(engine, adopt_legacy=args.adopt_legacy)
    print('Database migrations are current.')


if __name__ == '__main__':
    main()
