import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class Role(str, enum.Enum):
    student = "student"
    admin = "admin"


class ProjectType(str, enum.Enum):
    static = "static"
    fullstack = "fullstack"
    app = "app"


class ProjectStatus(str, enum.Enum):
    empty = "empty"
    building = "building"
    running = "running"
    sleeping = "sleeping"
    stopped = "stopped"
    failed = "failed"


class SourceKind(str, enum.Enum):
    zip = "zip"
    html = "html"
    git = "git"
    apk = "apk"


class ReleaseState(str, enum.Enum):
    queued = "queued"
    validating = "validating"
    building = "building"
    deploying = "deploying"
    active = "active"
    failed = "failed"
    superseded = "superseded"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True)
    student_no: Mapped[str | None] = mapped_column(String(4), unique=True)
    name: Mapped[str] = mapped_column(Text, default="")
    role: Mapped[Role] = mapped_column(_enum(Role, "user_role"), default=Role.student)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    student_no: Mapped[str] = mapped_column(String(4), unique=True)
    # 학생이 정하는 링크 이름 (/students/{slug}). 기본값은 학번. 내부 식별자는 계속 student_no.
    slug: Mapped[str] = mapped_column(String(32), unique=True)
    type: Mapped[ProjectType | None] = mapped_column(_enum(ProjectType, "project_type"))
    title: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    active_release_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("releases.id", ondelete="SET NULL", use_alter=True)
    )
    status: Mapped[ProjectStatus] = mapped_column(
        _enum(ProjectStatus, "project_status"), default=ProjectStatus.empty
    )
    last_request_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Release(Base):
    __tablename__ = "releases"
    __table_args__ = (UniqueConstraint("project_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    type: Mapped[ProjectType] = mapped_column(_enum(ProjectType, "project_type"))
    source_kind: Mapped[SourceKind] = mapped_column(_enum(SourceKind, "source_kind"))
    source_ref: Mapped[str] = mapped_column(Text)
    state: Mapped[ReleaseState] = mapped_column(
        _enum(ReleaseState, "release_state"), default=ReleaseState.queued
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EnvVar(Base):
    __tablename__ = "env_vars"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value_enc: Mapped[bytes] = mapped_column(LargeBinary)
    secret: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlatformSetting(Base):
    """관리자 설정(업로드 마감, 리소스 한도). 명세의 5개 테이블 외 추가분."""

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
