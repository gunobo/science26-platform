import csv
import io
import json
import re
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.config import get_settings
from app.db import get_db
from app.errors import APIError, not_found, upload_invalid
from app.models import AuditLog, Project, Release, User
from app.queue import claim_runtime_action, enqueue
from app.redis_client import redis
from app.security import admin_user, audit
from app.services.projects import project_out, student_url

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/projects")
async def all_projects(_: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(Project, User).join(User, User.id == Project.owner_id).order_by(Project.student_no)
    )
    out = []
    for project, owner in rows:
        active = await db.get(Release, project.active_release_id) if project.active_release_id else None
        stats = await redis.get(f"stats:{project.student_no}")
        out.append({
            **project_out(project, active),
            "owner": {"email": owner.email, "name": owner.name},
            "stats": json.loads(stats) if stats else None,
        })
    return out


@router.get("/students")
async def students(_: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    """학번이 등록된 학생 전원과 제출 현황 (프로젝트가 없는 학생도 포함).

    학번 4자리 = 학년 1자리 + 반 1자리 + 번호 2자리 (예: 1411 → 1학년 4반 11번).
    """
    rows = await db.execute(
        select(User, Project).outerjoin(Project, Project.owner_id == User.id)
        .where(User.student_no.is_not(None)).order_by(User.student_no)
    )
    out = []
    for user, project in rows:
        if project is None:
            state = "not_logged_in" if user.last_login_at is None else "no_upload"
        elif project.active_release_id:
            state = "deployed"
        elif project.status.value in ("building",):
            state = "building"
        else:
            state = "failed"
        out.append({
            "student_no": user.student_no,
            "grade": user.student_no[0],
            "class": user.student_no[1],
            "number": user.student_no[2:],
            "name": user.name,
            "email": user.email,
            "logged_in": user.last_login_at is not None,
            "is_test": user.is_test,
            "state": state,
            "project": None if project is None else {
                "slug": project.slug, "title": project.title, "type": project.type.value if project.type else None,
                "status": project.status.value, "url": student_url(project.slug) if project.active_release_id else None,
            },
        })
    return out


@router.get("/system")
async def system(_: User = Depends(admin_user)):
    usage = shutil.disk_usage(get_settings().data_dir)
    return {"disk": {"used": usage.used, "total": usage.total, "block_ratio": get_settings().disk_block_ratio}}


@router.post("/projects/{student_no}/stop", status_code=202)
async def force_stop(student_no: str, admin: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    project = (await db.execute(select(Project).where(Project.student_no == student_no))).scalar_one_or_none()
    if project is None:
        raise not_found()
    await claim_runtime_action(student_no)
    audit(db, admin, "admin_stop", student_no)
    await db.commit()
    await enqueue("stop_project", student_no, "stopped")
    return {"ok": True}


@router.delete("/projects/{student_no}", status_code=202)
async def delete_project(student_no: str, admin: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    project = (await db.execute(select(Project).where(Project.student_no == student_no))).scalar_one_or_none()
    if project is None:
        raise not_found()
    audit(db, admin, "delete", student_no)
    await db.commit()
    await enqueue("delete_project", student_no)
    return {"ok": True}


@router.post("/users/import")
async def import_users(
    file: UploadFile = File(...), admin: User = Depends(admin_user), db: AsyncSession = Depends(get_db)
):
    """CSV: email,학번,이름 (헤더 있어도 됨)."""
    text = (await file.read()).decode("utf-8-sig")
    created, updated, errors = 0, 0, []
    for lineno, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        if not row or not any(c.strip() for c in row):
            continue
        if lineno == 1 and "@" not in row[0]:
            continue  # 헤더
        if len(row) < 2:
            errors.append({"line": lineno, "message": "email,학번,이름 형식이 아닙니다"})
            continue
        email, student_no = row[0].strip().lower(), row[1].strip()
        name = row[2].strip() if len(row) > 2 else ""
        if "@" not in email or not re.fullmatch(r"\d{4}", student_no):
            errors.append({"line": lineno, "message": f"잘못된 값: {email}, {student_no}"})
            continue
        holder = (await db.execute(select(User).where(User.student_no == student_no))).scalar_one_or_none()
        if holder and holder.email != email:
            errors.append({"line": lineno, "message": f"학번 {student_no} 은 이미 {holder.email} 에 매핑됨"})
            continue
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            db.add(User(email=email, student_no=student_no, name=name))
            created += 1
        else:
            if user.student_no and user.student_no != student_no:
                errors.append({"line": lineno, "message": f"{email} 은 이미 학번 {user.student_no}"})
                continue
            user.student_no = student_no
            user.name = name or user.name
            updated += 1
        await db.flush()
    audit(db, admin, "import_users", f"{created}+{updated}")
    await db.commit()
    return {"created": created, "updated": updated, "errors": errors}


class StudentIn(BaseModel):
    email: str
    student_no: str
    name: str = ""
    is_test: bool = False


@router.post("/users", status_code=201)
async def add_student(body: StudentIn, admin: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    """학생 한 명 추가. is_test 면 학교 도메인이 아닌 구글 계정도 학생으로 로그인할 수 있다."""
    email, no = body.email.strip().lower(), body.student_no.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise APIError(400, "UPLOAD_INVALID", "이메일 형식이 올바르지 않습니다")
    if not re.fullmatch(r"\d{4}", no):
        raise APIError(400, "UPLOAD_INVALID", "학번은 숫자 4자리입니다")
    holder = await db.scalar(select(User).where(User.student_no == no))
    if holder and holder.email != email:
        raise APIError(409, "CONFLICT", f"학번 {no} 은 이미 {holder.email} 에 연결돼 있어요")
    user = await db.scalar(select(User).where(User.email == email))
    if user and user.student_no and user.student_no != no:
        raise APIError(409, "CONFLICT", f"{email} 은 이미 학번 {user.student_no} 이에요")
    if user is None:
        user = User(email=email)
        db.add(user)
    user.student_no, user.name, user.is_test = no, body.name.strip() or user.name, body.is_test
    audit(db, admin, "add_test_user" if body.is_test else "add_user", f"{no} {email}")
    await db.commit()
    return {"student_no": no, "email": email, "is_test": body.is_test}


@router.delete("/users/{student_no}", status_code=202)
async def delete_test_student(student_no: str, admin: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    """테스트 계정만 지울 수 있다 (프로젝트·DB·이미지까지). 실제 학생은 프로젝트 삭제만 한다."""
    user = await db.scalar(select(User).where(User.student_no == student_no))
    if user is None:
        raise not_found()
    if not user.is_test:
        raise APIError(403, "FORBIDDEN", "실제 학생 계정은 여기서 지울 수 없어요")
    await enqueue("delete_project", student_no)
    audit(db, admin, "delete_test_user", f"{student_no} {user.email}")
    await db.delete(user)
    await db.commit()
    return {"ok": True}


@router.get("/users")
async def list_users(_: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(User).order_by(User.student_no.nulls_last(), User.email))).scalars()
    return [
        {"email": u.email, "name": u.name, "student_no": u.student_no, "role": u.role.value}
        for u in rows
    ]


@router.get("/settings")
async def get_settings_(_: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    return await settings_store.load(db)


@router.put("/settings")
async def put_settings(
    cfg: settings_store.PlatformConfig, admin: User = Depends(admin_user), db: AsyncSession = Depends(get_db)
):
    if not (64 <= cfg.memory_mb <= 2048 and 64 <= cfg.stack_memory_mb <= 4096
            and 0.1 <= cfg.cpus <= 4 and 32 <= cfg.pids <= 1024):
        raise upload_invalid("리소스 한도 값이 허용 범위를 벗어났습니다")
    await settings_store.save(db, cfg)
    audit(db, admin, "settings", "")
    await db.commit()
    return cfg


# 관리자 화면 '최근 활동' 필터 → action 묶음
ACTIVITY_KINDS = {
    "login": ["first_login"],
    "project": ["register", "upload", "update_info", "rollback", "slug", "env", "stop", "start", "self_delete"],
    "admin": ["admin_stop", "delete", "import_users", "settings"],
}
TODAY_ACTIONS = ["first_login", "register", "upload", "update_info"]
KST = ZoneInfo("Asia/Seoul")


@router.get("/audit-logs")
async def audit_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    kind: str = Query("all", pattern="^(all|login|project|admin)$"),
    _: User = Depends(admin_user),
    db: AsyncSession = Depends(get_db),
):
    cond = AuditLog.action.in_(ACTIVITY_KINDS[kind]) if kind != "all" else true()
    total = await db.scalar(select(func.count()).select_from(AuditLog).where(cond))
    rows = await db.execute(
        select(AuditLog, User).outerjoin(User, User.id == AuditLog.actor_id).where(cond)
        .order_by(AuditLog.id.desc()).offset((page - 1) * size).limit(size)
    )
    # 오늘(한국 시간) 집계는 페이지·필터와 상관없이
    start = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    today = dict((await db.execute(
        select(AuditLog.action, func.count()).where(AuditLog.action.in_(TODAY_ACTIONS), AuditLog.at >= start)
        .group_by(AuditLog.action)
    )).all())
    return {
        "items": [
            {
                "at": log.at.isoformat(), "action": log.action, "target": log.target, "detail": log.detail,
                "actor": u.email if u else None, "actor_name": u.name if u else None,
                "actor_student_no": u.student_no if u else None,
            }
            for log, u in rows
        ],
        "total": total, "page": page, "size": size,
        "today": {a: today.get(a, 0) for a in TODAY_ACTIONS},
    }
