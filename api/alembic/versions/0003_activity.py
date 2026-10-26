"""users.last_login_at (첫 접속 알림), audit_logs.detail (활동 내용)

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True)))
    op.add_column("audit_logs", sa.Column("detail", sa.Text, nullable=False, server_default=""))
    # 이미 로그인한 적 있는 계정(관리자 등)에 첫 접속 알림이 한꺼번에 가지 않게, 기존 세션 기록이 있는 계정은 접속한 것으로 본다.
    # CSV 로만 등록되고 아직 로그인하지 않은 학생은 NULL 로 남아 첫 접속 때 알림이 간다.
    op.execute(
        "UPDATE users SET last_login_at = created_at WHERE role = 'admin' "
        "OR id IN (SELECT owner_id FROM projects)"
    )


def downgrade() -> None:
    op.drop_column("audit_logs", "detail")
    op.drop_column("users", "last_login_at")
