"""Version the original Stage 1 schema."""
from alembic import op
from app.migrations.baseline import metadata

revision = '0001_baseline'
down_revision = None
branch_labels = depends_on = None


def upgrade():
    # checkfirst=False deliberately rejects unversioned existing tables.
    metadata().create_all(op.get_bind(), checkfirst=False)


def downgrade():
    raise RuntimeError('Destructive baseline downgrade is unsupported; restore a verified backup instead.')
