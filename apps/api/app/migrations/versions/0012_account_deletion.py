"""Durable account disablement and scoped media cleanup; preserve live accounts."""
from alembic import op
import sqlalchemy as sa
revision='0012_account_deletion'
down_revision='0011_direct_uploads'
branch_labels=depends_on=None


def upgrade():
    op.add_column('users',sa.Column('deleted_at',sa.DateTime(timezone=True),nullable=True))
    op.create_table('account_deletions',
        sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id'),primary_key=True),
        sa.Column('receipt_hash',sa.String(64),nullable=False,unique=True),
        sa.Column('receipt_expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('requested_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('cleanup_after',sa.DateTime(timezone=True),nullable=False),
        sa.Column('attempted_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('media_cleaned_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('namespaces',sa.Text(),nullable=False))


def downgrade():
    raise RuntimeError('Restore verified DB/media backups; account deletion cannot be undone safely')
