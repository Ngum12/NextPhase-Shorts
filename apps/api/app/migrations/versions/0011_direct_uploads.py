"""Opt-in signed temporary chunks; preserve existing API upload sessions."""
from alembic import op
import sqlalchemy as sa
revision = '0011_direct_uploads'
down_revision = '0010_object_backend'
branch_labels = depends_on = None


def upgrade():
    op.add_column('upload_sessions', sa.Column('transfer_backend', sa.String(16), nullable=False, server_default='api'))
    op.add_column('upload_sessions', sa.Column('object_store_id', sa.String(64), nullable=True))
    op.add_column('upload_sessions', sa.Column('direct_cleanup_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('upload_parts', sa.Column('object_reference', sa.Text(), nullable=True))
    op.add_column('upload_parts', sa.Column('direct_grant_id', sa.String(36), nullable=True))
    op.create_table('direct_upload_grants',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('upload_sessions.id'), nullable=False),
        sa.Column('offset', sa.Integer(), nullable=False), sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_direct_upload_grants_session_id', 'direct_upload_grants', ['session_id'])
    op.create_index('uq_direct_upload_offset', 'direct_upload_grants', ['session_id', 'offset'], unique=True)


def downgrade():
    raise RuntimeError('Restore a verified DB/media backup; signed upload state cannot be discarded safely')
