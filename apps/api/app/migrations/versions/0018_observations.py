"""Private bounded-schema observations; historical measurements remain unknown."""
from alembic import op
import sqlalchemy as sa
revision='0018_observations'
down_revision='0017_queue_supervision'
branch_labels=depends_on=None

def upgrade():
    op.add_column('render_jobs',sa.Column('trace_id',sa.String(32),nullable=True))
    op.add_column('render_jobs',sa.Column('parent_span_id',sa.String(16),nullable=True))
    op.create_table('observations',
        sa.Column('id',sa.String(16),primary_key=True),
        sa.Column('trace_id',sa.String(32),nullable=False),
        sa.Column('parent_id',sa.String(16),nullable=True),
        sa.Column('job_id',sa.String(36),sa.ForeignKey('render_jobs.id'),nullable=True),
        sa.Column('attempt_id',sa.String(36),sa.ForeignKey('render_attempts.id'),nullable=True),
        sa.Column('stage',sa.String(32),nullable=False),
        sa.Column('started_ns',sa.BigInteger,nullable=False),
        sa.Column('ended_ns',sa.BigInteger,nullable=False),
        sa.Column('outcome',sa.String(16),nullable=False),
        sa.Column('attributes',sa.Text,nullable=False))
    for column in ('trace_id','job_id','started_ns'):op.create_index('ix_observations_'+column,'observations',[column])
    op.create_table('artifact_measures',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('job_id',sa.String(36),sa.ForeignKey('render_jobs.id'),nullable=False),
        sa.Column('kind',sa.String(16),nullable=False),
        sa.Column('bytes',sa.BigInteger,nullable=False),
        sa.Column('stored_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_artifact_measures_job_id','artifact_measures',['job_id'])

def downgrade():
    raise RuntimeError('Restore verified backups to downgrade observations')
