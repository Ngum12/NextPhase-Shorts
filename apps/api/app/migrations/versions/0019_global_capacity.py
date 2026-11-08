"""Shared admission mutex and conservative in-flight upload reservations."""
from alembic import op
import sqlalchemy as sa
revision='0019_global_capacity'
down_revision='0018_observations'
branch_labels=depends_on=None

def upgrade():
    op.create_table('capacity_gate',sa.Column('id',sa.Integer,primary_key=True))
    op.execute('INSERT INTO capacity_gate (id) VALUES (1)')
    op.create_table('ingress_leases',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('reserved_bytes',sa.BigInteger,nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('deadline_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_ingress_leases_deadline_at','ingress_leases',['deadline_at'])

def downgrade():raise RuntimeError('Restore verified backups to downgrade capacity state')
