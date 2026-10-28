import asyncio
import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.db import get_db
from app.errors import not_found
from app.models import Project, Release, ReleaseState, Role, User
from app.redis_client import redis
from app.security import current_user
from app.services import buildlog

router = APIRouter(tags=["me"])

TERMINAL = {ReleaseState.active, ReleaseState.failed, ReleaseState.superseded}


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return {
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
        "student_no": user.student_no,
        "mapped": user.student_no is not None,
    }


@router.get("/notice")
async def notice(_: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """대시보드 위 공지와 업로드 마감. 로그인한 사람에게만 보인다."""
    cfg = await settings_store.load(db)
    return {"notice": cfg.notice, "upload_deadline": cfg.upload_deadline}


@router.get("/releases/{release_id}/logs")
async def release_logs(
    release_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    release = await db.get(Release, release_id)
    if release is None:
        raise not_found()
    project = await db.get(Project, release.project_id)
    if user.role != Role.admin and project.owner_id != user.id:
        raise not_found()
    finished = release.state in TERMINAL
    final_state = release.state.value
    error = release.error

    async def stream():
        key = buildlog.key(release_id)
        last = "0"
        idle = 0
        while True:
            res = await redis.xread({key: last}, count=200, block=15000)
            if not res:
                if finished:
                    # 로그가 만료됐거나 없는 완료 릴리스
                    yield _sse({"kind": "end", "line": final_state, "error": error})
                    return
                idle += 1
                yield ": keep-alive\n\n"
                if idle > 80:  # 20분
                    return
                continue
            idle = 0
            for entry_id, fields in res[0][1]:
                last = entry_id
                yield _sse(fields)
                if fields.get("kind") == "end":
                    return
            await asyncio.sleep(0)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
