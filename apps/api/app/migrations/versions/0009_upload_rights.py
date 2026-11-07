"""Record explicit acknowledgements without inventing historical consent."""
from alembic import op
import sqlalchemy as sa
revision='0009_upload_rights'
down_revision='0008_storage_budgets'
branch_labels=depends_on=None


def upgrade():
    for table in ('render_jobs','upload_sessions'):
        op.add_column(table,sa.Column('rights_version',sa.String(64),nullable=True))
        op.add_column(table,sa.Column('rights_confirmed_at',sa.DateTime(timezone=True),nullable=True))


def downgrade():
    raise RuntimeError('Restore a verified backup rather than discarding acknowledgement records.')
