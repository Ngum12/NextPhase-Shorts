"""Optional private Gemini selection metadata; no duplicate transcript or provider output."""
from alembic import op
import sqlalchemy as sa
revision='0026_gemini_selection'
down_revision='0025_scene_analysis'
branch_labels=depends_on=None


def upgrade():
    with op.batch_alter_table('project_analyses') as batch:
        batch.add_column(sa.Column('gemini_selection_json',sa.Text(),nullable=True))


def downgrade():raise RuntimeError('Use verified matching-code backups to downgrade Gemini selection')
