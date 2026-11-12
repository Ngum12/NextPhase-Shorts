"""Optional source-bound visual-change guidance; no persistent proxy frames."""
from alembic import op
import sqlalchemy as sa
revision='0025_scene_analysis'
down_revision='0024_audio_timing'
branch_labels=depends_on=None


def upgrade():
    with op.batch_alter_table('project_analyses') as batch:
        batch.add_column(sa.Column('scene_analysis_json',sa.Text(),nullable=True))


def downgrade():raise RuntimeError('Use verified matching-code backups to downgrade visual analysis')
