"""Worker liveness metadata only; never modifies jobs or user media."""
from alembic import op
import sqlalchemy as sa
revision='0013_worker_pulses'
down_revision='0012_account_deletion'
branch_labels=depends_on=None


def upgrade():
    op.create_table('worker_pulses',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('started_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('heartbeat_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('stopped_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('phase',sa.String(24),nullable=False),
        sa.Column('heartbeat_seconds',sa.Float(),nullable=False))
    op.create_index('ix_worker_pulses_heartbeat_at','worker_pulses',['heartbeat_at'])


def downgrade():
    op.drop_index('ix_worker_pulses_heartbeat_at',table_name='worker_pulses')
    op.drop_table('worker_pulses')
