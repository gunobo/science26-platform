import html
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errors import not_found
from app.models import Project, ProjectStatus, User
from app.redis_client import redis
from app.queue import enqueue
from app.services.projects import base_path, project_out, thumbnail_url

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/projects")
async def public_projects(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(Project, User.name)
        .join(User, User.id == Project.owner_id)
        .where(Project.active_release_id.is_not(None))
        .order_by(Project.student_no)
    )
    out = []
    for project, name in rows:
        card = project_out(project)
        out.append({
            "student_no": project.student_no,
            "slug": project.slug,
            "name": name,
            "title": project.title or f"{project.student_no} 프로젝트",
            "description": project.description,
            "type": card["type"],
            "status": card["status"],
            "thumbnail_url": thumbnail_url(project),
            "url": card["url"],
        })
    return out


@router.get("/thumbnails/{student_no}")
async def thumbnail(student_no: str, db: AsyncSession = Depends(get_db)):
    project = (await db.execute(select(Project).where(Project.student_no == student_no))).scalar_one_or_none()
    if project is None or not project.thumbnail_path or not Path(project.thumbnail_path).is_file():
        raise not_found()
    return FileResponse(project.thumbnail_path, headers={"Cache-Control": "public, max-age=300"})


def _page(title: str, body: str, refresh: int | None = None, status: int = 200) -> HTMLResponse:
    meta = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    return HTMLResponse(
        f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">{meta}<title>{html.escape(title)}</title>
<style>body{{font-family:system-ui,sans-serif;display:grid;place-items:center;min-height:100vh;margin:0;
background:#f6f7f9;color:#222}}main{{text-align:center;padding:24px}}h1{{font-size:22px}}
p{{color:#666}}a{{color:#2563eb}}@media(prefers-color-scheme:dark){{body{{background:#111;color:#eee}}p{{color:#aaa}}}}
</style></head><body><main><h1>{html.escape(title)}</h1><p>{body}</p>
<p><a href="/">science26 전체 목록</a></p></main></body></html>""",
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/wake/{key}")
async def wake(key: str, db: AsyncSession = Depends(get_db)):
    """학생 라우터가 없을 때 Traefik 폴백이 보내는 요청. key 는 링크 이름 또는 학번."""
    project = (
        await db.execute(select(Project).where(or_(Project.slug == key, Project.student_no == key)))
    ).scalar_one_or_none()
    if project is None:
        return _page("페이지를 찾을 수 없습니다", "아직 배포되지 않았거나 없는 주소입니다.", status=404)
    if key != project.slug:
        # 학번이나 예전 주소로 들어오면 현재 링크 이름으로 보낸다
        return RedirectResponse(f"{base_path(project.slug)}/", status_code=302)
    if not project.active_release_id:
        if project.status == ProjectStatus.building:
            return _page("배포 준비 중", "첫 빌드가 진행 중입니다. 잠시 후 자동으로 새로고침됩니다.", refresh=10)
        return _page("페이지를 찾을 수 없습니다", "아직 배포되지 않은 프로젝트입니다.", status=404)
    if project.status == ProjectStatus.stopped:
        return _page("중지된 프로젝트", "학생 또는 관리자가 이 프로젝트를 중지했습니다.", status=503)
    if project.status == ProjectStatus.sleeping:
        if await redis.set(f"wake:{project.student_no}", "1", nx=True, ex=60):
            await enqueue("start_project", project.student_no)
        return _page("깨우는 중…", "한동안 방문이 없어 잠들어 있던 프로젝트를 켜고 있어요. 곧 자동으로 열립니다.", refresh=4)
    # running/building 인데 라우터가 아직 안 붙은 짧은 순간
    return _page("잠시만요", "프로젝트를 여는 중입니다.", refresh=3)
