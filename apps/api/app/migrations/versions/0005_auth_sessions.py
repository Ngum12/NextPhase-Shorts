"""Persistent revocation and atomic authentication rate windows."""
from alembic import op
import sqlalchemy as sa
revision = '0005_auth_sessions'
down_revision = '0004_upload_sessions'
branch_labels = depends_on = None


def upgrade():
    op.create_table('auth_sessions',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_auth_sessions_user_id', 'auth_sessions', ['user_id'])
    op.create_index('ix_auth_sessions_expires_at', 'auth_sessions', ['expires_at'])
    op.create_table('auth_rate_buckets',
        sa.Column('key', sa.String(64), primary_key=True),
        sa.Column('attempts', sa.Integer, nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_auth_rate_buckets_expires_at', 'auth_rate_buckets', ['expires_at'])


def downgrade():
    raise RuntimeError('Restore a verified backup; do not silently discard revocation history.')
