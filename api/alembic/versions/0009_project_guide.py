"""projects.guide_path, projects.guide_name: 이용 가이드북 파일

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("guide_path", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("guide_name", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("projects", "guide_name")
    op.drop_column("projects", "guide_path")
