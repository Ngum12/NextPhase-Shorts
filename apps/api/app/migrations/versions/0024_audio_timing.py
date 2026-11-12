"""Source-bound optional low-energy timing metadata for private review."""
from alembic import op
import sqlalchemy as sa
revision='0024_audio_timing'
down_revision='0023_english_analysis'
branch_labels=depends_on=None


def upgrade():
    with op.batch_alter_table('project_analyses') as batch:
        batch.add_column(sa.Column('audio_timing_json',sa.Text(),nullable=True))


def downgrade():raise RuntimeError('Use verified matching-code backups to downgrade audio timing')
