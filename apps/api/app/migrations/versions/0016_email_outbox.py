"""Encrypted durable auth email and method-tagged verification; preserve legacy proof meaning."""
from alembic import op
import sqlalchemy as sa
revision='0016_email_outbox'
down_revision='0015_refresh_sessions'
branch_labels=depends_on=None


def upgrade():
    op.add_column('auth_actions',sa.Column('delivery_method',sa.String(16),server_default='local_file',nullable=False))
    op.create_table('mail_outbox',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('action_id',sa.String(36),sa.ForeignKey('auth_actions.id'),nullable=False,unique=True),
        sa.Column('payload',sa.Text,nullable=True),
        sa.Column('state',sa.String(16),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('due_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('attempts',sa.Integer,nullable=False),
        sa.Column('lease_token',sa.String(36),nullable=True),
        sa.Column('lease_until',sa.DateTime(timezone=True),nullable=True),
        sa.Column('last_code',sa.String(32),nullable=True))
    for field in ('user_id','state','expires_at','due_at'):
        op.create_index('ix_mail_outbox_'+field,'mail_outbox',[field])
    op.create_table('mail_budgets',
        sa.Column('id',sa.String(16),primary_key=True),
        sa.Column('day',sa.String(10),nullable=False),
        sa.Column('month',sa.String(7),nullable=False),
        sa.Column('daily_attempts',sa.Integer,nullable=False),
        sa.Column('monthly_attempts',sa.Integer,nullable=False),
        sa.Column('next_send_at',sa.DateTime(timezone=True),nullable=False))


def downgrade():
    raise RuntimeError('Restore verified backups to downgrade encrypted email outbox metadata')
