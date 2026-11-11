"""Source-linked immutable selected-excerpt jobs in the existing render queue."""
from alembic import op
import sqlalchemy as sa
revision='0022_excerpt_previews'
down_revision='0021_project_analysis'
branch_labels=depends_on=None


def upgrade():
    with op.batch_alter_table('render_jobs') as batch:
        batch.add_column(sa.Column('preview_parent_id',sa.String(36),nullable=True))
        batch.add_column(sa.Column('preview_spec_json',sa.Text,nullable=True))
        batch.create_foreign_key('fk_preview_parent','render_jobs',['preview_parent_id'],['id'])
        batch.create_index('ix_render_jobs_preview_parent_id',['preview_parent_id'])


def downgrade():raise RuntimeError('Restore verified backups to downgrade excerpt previews')
