"""Explicit queued work kinds and durable upload analysis consent."""
from alembic import op
import sqlalchemy as sa
revision='0023_english_analysis'
down_revision='0022_excerpt_previews'
branch_labels=depends_on=None


def upgrade():
    with op.batch_alter_table('render_jobs') as batch:
        batch.add_column(sa.Column('operation',sa.String(16),nullable=False,server_default='render'))
    op.execute("UPDATE render_jobs SET operation='preview' WHERE preview_parent_id IS NOT NULL")
    with op.batch_alter_table('upload_sessions') as batch:
        batch.add_column(sa.Column('english_analysis',sa.Boolean(),nullable=False,server_default=sa.false()))


def downgrade():raise RuntimeError('Use verified matching-code backups to downgrade analysis jobs')
