"""Owner-scoped idempotency for job submissions."""
from alembic import op
import sqlalchemy as sa

revision = '0003_submission_keys'
down_revision = '0002_job_leases'
branch_labels = depends_on = None


def upgrade():
    op.add_column('render_jobs', sa.Column('idempotency_key', sa.String(128), nullable=True))
    op.add_column('render_jobs', sa.Column('request_hash', sa.String(64), nullable=True))
    op.create_index('uq_render_jobs_owner_submission', 'render_jobs', ['user_id', 'idempotency_key'], unique=True)


def downgrade():
    raise RuntimeError('Restore a verified backup rather than discarding submission history.')
