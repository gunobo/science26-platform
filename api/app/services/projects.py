"""라우터들이 같이 쓰는 프로젝트 조회·직렬화."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Project, Release, User


async def get_project(db: AsyncSession, student_no: str) -> Project | None:
    return (
        await db.execute(select(Project).where(Project.student_no == student_no))
    ).scalar_one_or_none()


async def get_or_create_project(db: AsyncSession, user: User) -> Project:
    project = await get_project(db, user.student_no)
    if project is None:
        project = Project(owner_id=user.id, student_no=user.student_no, slug=user.student_no)
        db.add(project)
        await db.flush()
    return project


async def next_version(db: AsyncSession, project: Project) -> int:
    current = await db.scalar(select(func.max(Release.version)).where(Release.project_id == project.id))
    return (current or 0) + 1


def base_path(slug: str) -> str:
    return f"/students/{slug}"


def student_url(slug: str) -> str:
    return f"{get_settings().public_url}{base_path(slug)}/"


def thumbnail_url(project: Project) -> str | None:
    if not project.thumbnail_path:
        return None
    return f"{get_settings().upload_url}/api/v1/public/thumbnails/{project.student_no}"


def release_out(r: Release | None) -> dict | None:
    if r is None:
        return None
    return {
        "id": str(r.id),
        "version": r.version,
        "type": r.type.value,
        "source_kind": r.source_kind.value,
        "source_ref": r.source_ref if r.source_kind.value == "git" else r.source_ref.rsplit("/", 1)[-1],
        "state": r.state.value,
        "error": r.error,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    }


def project_out(p: Project, active: Release | None = None, latest: Release | None = None) -> dict:
    return {
        "student_no": p.student_no,
        "slug": p.slug,
        "type": p.type.value if p.type else None,
        "title": p.title,
        "description": p.description,
        "thumbnail_url": thumbnail_url(p),
        "status": p.status.value,
        "url": student_url(p.slug),
        "last_request_at": p.last_request_at.isoformat() if p.last_request_at else None,
        "active_release": release_out(active),
        "latest_release": release_out(latest),
    }
