"""Single-use local-development email action proofs; no verified-user backfill."""
from alembic import op
import sqlalchemy as sa
revision='0014_auth_actions'
down_revision='0013_worker_pulses'
branch_labels=depends_on=None


def upgrade():
    op.add_column('users',sa.Column('email_verified_at',sa.DateTime(timezone=True),nullable=True))
    op.add_column('users',sa.Column('email_verification_method',sa.String(24),nullable=True))
    op.create_table('auth_actions',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('purpose',sa.String(16),nullable=False),
        sa.Column('token_hash',sa.String(64),nullable=False,unique=True),
        sa.Column('account_digest',sa.String(64),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('used_at',sa.DateTime(timezone=True),nullable=True))
    op.create_index('ix_auth_actions_user_id','auth_actions',['user_id'])
    op.create_index('ix_auth_actions_expires_at','auth_actions',['expires_at'])


def downgrade():
    raise RuntimeError('Restore verified backups to downgrade authentication action metadata')
