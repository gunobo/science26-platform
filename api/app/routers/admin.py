import csv
import io
import json
import re

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.db import get_db
from app.errors import not_found, upload_invalid
from app.models import AuditLog, Project, Release, User
from app.queue import enqueue
from app.redis_client import redis
from app.security import admin_user, audit
from app.services.projects import project_out

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


@router.post("/projects/{student_no}/stop", status_code=202)
async def force_stop(student_no: str, admin: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    project = (await db.execute(select(Project).where(Project.student_no == student_no))).scalar_one_or_none()
    if project is None:
        raise not_found()
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


@router.get("/audit-logs")
async def audit_logs(_: User = Depends(admin_user), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(AuditLog, User.email).outerjoin(User, User.id == AuditLog.actor_id)
        .order_by(AuditLog.id.desc()).limit(200)
    )
    return [
        {"at": log.at.isoformat(), "actor": email, "action": log.action, "target": log.target}
        for log, email in rows
    ]
