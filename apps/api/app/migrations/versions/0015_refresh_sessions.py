"""Add refresh families without invalidating legacy bearer sessions."""
from alembic import op
import sqlalchemy as sa

revision = '0015_refresh_sessions'
down_revision = '0014_auth_actions'
branch_labels = depends_on = None


def upgrade():
    op.add_column('auth_sessions', sa.Column('family_id', sa.String(36), nullable=True))
    op.create_index('ix_auth_sessions_family_id', 'auth_sessions', ['family_id'])
    op.create_table('refresh_families',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_refresh_families_user_id', 'refresh_families', ['user_id'])
    op.create_index('ix_refresh_families_expires_at', 'refresh_families', ['expires_at'])
    op.create_table('refresh_grants',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('family_id', sa.String(36), sa.ForeignKey('refresh_families.id'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rotation_hash', sa.String(64), nullable=True),
        sa.Column('successor_hash', sa.String(64), nullable=True),
        sa.Column('access_session_id', sa.String(64), nullable=True))
    op.create_index('ix_refresh_grants_family_id', 'refresh_grants', ['family_id'])


def downgrade():
    raise RuntimeError('Restore verified backups to downgrade authentication sessions')
