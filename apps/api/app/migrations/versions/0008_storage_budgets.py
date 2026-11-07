"""Persist conservative per-upload/job retained-media reservations."""
from alembic import op
import sqlalchemy as sa
revision='0008_storage_budgets'
down_revision='0007_project_deletion'
branch_labels=depends_on=None


def upgrade():
    for table in ('render_jobs','upload_sessions'):
        op.add_column(table,sa.Column('storage_reserved_bytes',sa.BigInteger,nullable=True))
        op.add_column(table,sa.Column('max_render_bytes',sa.BigInteger,nullable=True))


def downgrade():
    raise RuntimeError('Restore a verified backup rather than discarding storage reservations.')
