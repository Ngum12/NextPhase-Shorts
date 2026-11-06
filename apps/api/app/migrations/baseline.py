"""Frozen Stage 1 schema; never import evolving application models here."""
import sqlalchemy as sa


def metadata():
    meta = sa.MetaData()
    sa.Table('users', meta,
             sa.Column('id', sa.String(36), primary_key=True),
             sa.Column('email', sa.String(320), nullable=False, unique=True, index=True),
             sa.Column('password_hash', sa.String(256), nullable=False),
             sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    sa.Table('render_jobs', meta,
             sa.Column('id', sa.String(36), primary_key=True),
             sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False, index=True),
             sa.Column('title', sa.String(120), nullable=False),
             sa.Column('style', sa.String(48), nullable=False),
             sa.Column('desired_seconds', sa.Integer, nullable=False),
             sa.Column('source_duration_seconds', sa.Float, nullable=False),
             sa.Column('source_path', sa.Text, nullable=False),
             sa.Column('output_path', sa.Text),
             sa.Column('status', sa.String(20), nullable=False, index=True),
             sa.Column('error_code', sa.String(80)),
             sa.Column('output_duration_seconds', sa.Float),
             sa.Column('attempt_count', sa.Integer, nullable=False),
             sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
             sa.Column('started_at', sa.DateTime(timezone=True)),
             sa.Column('finished_at', sa.DateTime(timezone=True)))
    return meta
