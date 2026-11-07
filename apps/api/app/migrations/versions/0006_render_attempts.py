"""Attempt-level timing records; no historical measurements are fabricated."""
from alembic import op
import sqlalchemy as sa
revision = '0006_render_attempts'
down_revision = '0005_auth_sessions'
branch_labels = depends_on = None


def upgrade():
    op.create_table('render_attempts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('render_jobs.id'), nullable=False),
        sa.Column('number', sa.Integer, nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('wall_seconds', sa.Float, nullable=True),
        sa.Column('output_bytes', sa.Integer, nullable=True))
    op.create_index('ix_render_attempts_job_id', 'render_attempts', ['job_id'])
    op.create_index('ix_render_attempts_started_at', 'render_attempts', ['started_at'])
    op.create_index('uq_render_attempt_number', 'render_attempts', ['job_id','number'], unique=True)


def downgrade():
    raise RuntimeError('Restore a verified backup rather than discarding timing history.')
