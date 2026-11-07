"""Preserve existing private-volume jobs; new admissions may opt into S3."""
from alembic import op
import sqlalchemy as sa

revision = '0010_object_backend'
down_revision = '0009_upload_rights'
branch_labels = depends_on = None


def upgrade():
    op.add_column('render_jobs', sa.Column('media_backend', sa.String(16),
                                        nullable=False, server_default='local'))
    op.add_column('render_jobs', sa.Column('object_store_id', sa.String(64), nullable=True))


def downgrade():
    raise RuntimeError('Restore a verified backup; remote media cannot be downgraded safely')
