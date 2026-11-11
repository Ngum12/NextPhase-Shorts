"""Private owner-bound English transcript review pilot; inference remains offline."""
from alembic import op
import sqlalchemy as sa

revision = '0021_project_analysis'
down_revision = '0020_restore_binding'
branch_labels = depends_on = None


def upgrade():
    op.create_table('project_analyses',
        sa.Column('job_id', sa.String(36), sa.ForeignKey('render_jobs.id'), primary_key=True),
        sa.Column('transcript_json', sa.Text, nullable=False),
        sa.Column('review_json', sa.Text, nullable=True),
        sa.Column('proposal_json', sa.Text, nullable=False),
        sa.Column('revision', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    raise RuntimeError('Restore verified backups to downgrade project analysis state')
