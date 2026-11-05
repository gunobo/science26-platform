"""projects.unit, projects.effect: 연관 단원·과학적 효과

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("unit", sa.Text(), nullable=False, server_default=""))
    op.add_column("projects", sa.Column("effect", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("projects", "effect")
    op.drop_column("projects", "unit")
