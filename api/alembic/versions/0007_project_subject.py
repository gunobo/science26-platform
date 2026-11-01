"""projects.subject: 물리학·화학·생명과학·지구과학 분류

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("subject", sa.String(16), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("projects", "subject")
