"""initial schema

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

user_role = pg.ENUM("student", "admin", name="user_role", create_type=False)
project_type = pg.ENUM("static", "fullstack", "app", name="project_type", create_type=False)
project_status = pg.ENUM(
    "empty", "building", "running", "sleeping", "stopped", "failed",
    name="project_status", create_type=False,
)
source_kind = pg.ENUM("zip", "html", "git", "apk", name="source_kind", create_type=False)
release_state = pg.ENUM(
    "queued", "validating", "building", "deploying", "active", "failed", "superseded",
    name="release_state", create_type=False,
)
ENUMS = [user_role, project_type, project_status, source_kind, release_state]


def upgrade() -> None:
    bind = op.get_bind()
    for e in ENUMS:
        e.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("student_no", sa.String(4), unique=True),
        sa.Column("name", sa.Text, nullable=False, server_default=""),
        sa.Column("role", user_role, nullable=False, server_default="student"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "projects",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_no", sa.String(4), nullable=False, unique=True),
        sa.Column("slug", sa.String(32), nullable=False, unique=True),
        sa.Column("type", project_type),
        sa.Column("title", sa.Text, nullable=False, server_default=""),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("thumbnail_path", sa.Text),
        sa.Column("active_release_id", pg.UUID(as_uuid=True)),
        sa.Column("status", project_status, nullable=False, server_default="empty"),
        sa.Column("last_request_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "releases",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("type", project_type, nullable=False),
        sa.Column("source_kind", source_kind, nullable=False),
        sa.Column("source_ref", sa.Text, nullable=False),
        sa.Column("state", release_state, nullable=False, server_default="queued"),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("project_id", "version"),
    )
    op.create_foreign_key(
        "projects_active_release_fk", "projects", "releases",
        ["active_release_id"], ["id"], ondelete="SET NULL",
    )
    op.create_table(
        "env_vars",
        sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value_enc", sa.LargeBinary, nullable=False),
        sa.Column("secret", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("actor_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("target", sa.Text, nullable=False, server_default=""),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "platform_settings",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", pg.JSONB, nullable=False),
    )


def downgrade() -> None:
    for t in ["platform_settings", "audit_logs", "env_vars"]:
        op.drop_table(t)
    op.drop_constraint("projects_active_release_fk", "projects")
    for t in ["releases", "projects", "users"]:
        op.drop_table(t)
    bind = op.get_bind()
    for e in reversed(ENUMS):
        e.drop(bind, checkfirst=True)
