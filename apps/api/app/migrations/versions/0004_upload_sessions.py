"""Durable sequential upload reservations and immutable verified parts."""
from alembic import op
import sqlalchemy as sa

revision = '0004_upload_sessions'
down_revision = '0003_submission_keys'
branch_labels = depends_on = None


def upgrade():
    op.create_table('upload_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('client_key', sa.String(128), nullable=False),
        sa.Column('descriptor_hash', sa.String(64), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('extension', sa.String(8), nullable=False),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('style', sa.String(48), nullable=False),
        sa.Column('desired_seconds', sa.Integer, nullable=False),
        sa.Column('total_bytes', sa.Integer, nullable=False),
        sa.Column('received_bytes', sa.Integer, nullable=False),
        sa.Column('chunk_bytes', sa.Integer, nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('render_jobs.id'), nullable=True),
        sa.Column('source_sha256', sa.String(64), nullable=True),
        sa.Column('parts_cleaned', sa.Boolean, nullable=False))
    op.create_index('uq_upload_sessions_owner_key', 'upload_sessions', ['user_id', 'client_key'], unique=True)
    op.create_index('ix_upload_sessions_user_id', 'upload_sessions', ['user_id'])
    op.create_index('ix_upload_sessions_expires_at', 'upload_sessions', ['expires_at'])
    op.create_table('upload_parts',
        sa.Column('session_id', sa.String(36), sa.ForeignKey('upload_sessions.id'), primary_key=True),
        sa.Column('offset', sa.Integer, primary_key=True),
        sa.Column('size', sa.Integer, nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False))


def downgrade():
    raise RuntimeError('Restore a verified backup rather than discarding upload state.')
