"""Fence render attempts and separate their output artifacts."""
from alembic import op
import sqlalchemy as sa

revision = '0002_job_leases'
down_revision = '0001_baseline'
branch_labels = depends_on = None


def upgrade():
    op.add_column('render_jobs', sa.Column('claim_token', sa.String(36), nullable=True))
    op.add_column('render_jobs', sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_render_jobs_lease_expires_at', 'render_jobs', ['lease_expires_at'])
    # All old workers MUST be stopped first. Preserve successes/download paths.
    op.execute(sa.text("UPDATE render_jobs SET status='queued', started_at=NULL WHERE status='processing' AND attempt_count < 2"))
    op.execute(sa.text("UPDATE render_jobs SET status='failed', error_code='MAX_RETRIES', finished_at=CURRENT_TIMESTAMP WHERE status='processing'"))


def downgrade():
    raise RuntimeError('Lease downgrade is unsupported; restore a verified backup instead.')
