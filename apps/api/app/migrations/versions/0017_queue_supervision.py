"""Durable broker signals, bounded claim supervision and explicit terminal failures."""
from alembic import op
import sqlalchemy as sa
revision='0017_queue_supervision'
down_revision='0016_email_outbox'
branch_labels=depends_on=None


def upgrade():
    op.add_column('render_jobs',sa.Column('claim_deadline_at',sa.DateTime(timezone=True),nullable=True))
    op.add_column('render_jobs',sa.Column('next_attempt_at',sa.DateTime(timezone=True),nullable=True))
    op.create_index('ix_render_jobs_next_attempt_at','render_jobs',['next_attempt_at'])
    op.execute("UPDATE render_jobs SET claim_deadline_at=lease_expires_at WHERE status='processing'")
    op.add_column('render_attempts',sa.Column('deadline_at',sa.DateTime(timezone=True),nullable=True))
    op.execute("""UPDATE render_attempts SET deadline_at=(SELECT claim_deadline_at FROM render_jobs
        WHERE render_jobs.claim_token=render_attempts.id) WHERE status='running'""")
    op.create_table('queue_signals',
        sa.Column('job_id',sa.String(36),sa.ForeignKey('render_jobs.id'),primary_key=True),
        sa.Column('generation',sa.String(36),unique=True,nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('published_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('completed_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('next_publish_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('lease_token',sa.String(36),nullable=True),
        sa.Column('lease_until',sa.DateTime(timezone=True),nullable=True))
    op.create_index('ix_queue_signals_next_publish_at','queue_signals',['next_publish_at'])
    op.create_table('render_dead_letters',
        sa.Column('job_id',sa.String(36),sa.ForeignKey('render_jobs.id'),primary_key=True),
        sa.Column('reason',sa.String(80),nullable=False),
        sa.Column('attempts',sa.Integer,nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_render_dead_letters_created_at','render_dead_letters',['created_at'])
    op.execute("""INSERT INTO render_dead_letters (job_id,reason,attempts,created_at)
        SELECT id,'LEGACY_FAILURE',attempt_count,COALESCE(finished_at,created_at) FROM render_jobs WHERE status='failed'""")


def downgrade():
    raise RuntimeError('Restore verified backups to downgrade durable queue state')
