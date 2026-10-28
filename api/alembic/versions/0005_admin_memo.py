"""users.admin_memo: 선생님만 보는 평가 메모

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("admin_memo", sa.Text, nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("users", "admin_memo")
