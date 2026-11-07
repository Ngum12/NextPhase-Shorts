"""Durable deletion tombstones and retryable media cleanup."""
from alembic import op
import sqlalchemy as sa
revision = '0007_project_deletion'
down_revision = '0006_render_attempts'
branch_labels = depends_on = None


def upgrade():
    for name in ('deleted_at','cleanup_after','media_deleted_at','cleanup_attempted_at'):
        op.add_column('render_jobs',sa.Column(name,sa.DateTime(timezone=True),nullable=True))
    op.create_index('ix_render_jobs_cleanup_after','render_jobs',['cleanup_after'])


def downgrade():
    raise RuntimeError('Restore a verified backup; do not discard deletion requests.')
