"""Bind protected database snapshots to their independent current journal stream."""
from alembic import op
import sqlalchemy as sa
revision='0020_restore_binding'
down_revision='0019_global_capacity'
branch_labels=depends_on=None

def upgrade():
    op.create_table('restore_journal_binding',
        sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('journal_id',sa.String(36),nullable=False),
        sa.Column('bound_at',sa.DateTime(timezone=True),nullable=False))

def downgrade():
    raise RuntimeError('Restore verified backups to downgrade journal binding')
