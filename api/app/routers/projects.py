import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.config import get_settings
from app.db import get_db
from app.errors import APIError, not_found, upload_invalid
from app.models import (
    EnvVar, Project, ProjectStatus, ProjectType, Release, ReleaseState, Role, SourceKind, User,
)
from app.queue import acquire_project_lock, enqueue, release_project_lock
from app.security import audit, decrypt, encrypt, mapped_student, rate_limit
from app.services import validation as v
from app.services.projects import get_or_create_project, get_project, next_version, project_out, release_out

router = APIRouter(prefix="/projects/me", tags=["projects"])

RESERVED_ENV = {"DATABASE_URL", "REDIS_URL", "BASE_PATH", "PUBLIC_URL"}
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


# ---- 조회·수정 ----

@router.get("")
async def my_project(user: User = Depends(mapped_student), db: AsyncSession = Depends(get_db)):
    project = await get_project(db, user.student_no)
    if project is None:
        return {"student_no": user.student_no, "slug": user.student_no, "status": "empty", "type": None, "listed": True,
                "title": "", "description": "", "thumbnail_url": None, "active_release": None,
                "latest_release": None, "url": None, "last_request_at": None}
    active = await db.get(Release, project.active_release_id) if project.active_release_id else None
    latest = (
        await db.execute(
            select(Release).where(Release.project_id == project.id).order_by(Release.version.desc()).limit(1)
        )
    ).scalar_one_or_none()
    return project_out(project, active, latest)


@router.patch("")
async def update_project(
    title: str | None = Form(None),
    description: str | None = Form(None),
    slug: str | None = Form(None),
    listed: bool | None = Form(None),
    thumbnail: UploadFile | None = File(None),
    user: User = Depends(mapped_student),
    db: AsyncSession = Depends(get_db),
):
    s = get_settings()
    project = await get_or_create_project(db, user)
    if title is not None:
        project.title = title.strip()[:100]
    if description is not None:
        project.description = description.strip()[:2000]
    if listed is not None:
        project.listed = listed

    slug_changed = False
    if slug is not None and slug != project.slug:
        try:
            v.check_slug(slug, user.student_no)
        except v.ValidationError as e:
            raise APIError(400, e.code, e.message)
        taken = await db.scalar(select(Project.id).where(Project.slug == slug, Project.id != project.id))
        if taken:
            raise APIError(409, "SLUG_TAKEN", "이미 다른 학생이 쓰는 링크 이름입니다")
        project.slug = slug
        slug_changed = True

    if thumbnail is not None and thumbnail.filename:
        data = await thumbnail.read()
        try:
            v.check_image(thumbnail.filename, len(data), s.max_image_bytes)
        except v.ValidationError as e:
            raise upload_invalid(e.message)
        s.thumbnails_dir.mkdir(parents=True, exist_ok=True)
        path = s.thumbnails_dir / f"{user.student_no}{Path(thumbnail.filename).suffix.lower()}"
        for old in s.thumbnails_dir.glob(f"{user.student_no}.*"):
            old.unlink()
        path.write_bytes(data)
        project.thumbnail_path = str(path)

    await db.commit()
    # 경로가 라우터 라벨에 박혀 있어서 링크 이름을 바꾸면 활성 릴리스를 다시 띄운다.
    if slug_changed and project.active_release_id:
        await _queue_redeploy(db, user, project, project.active_release_id, action="slug")
    return {"ok": True, "slug": project.slug, "redeploying": slug_changed and bool(project.active_release_id)}


@router.delete("", status_code=202)
async def delete_my_project(user: User = Depends(mapped_student), db: AsyncSession = Depends(get_db)):
    """내 프로젝트(스택, DB, 업로드 파일, 배포 기록) 전체 삭제. 마감 후에는 관리자만."""
    project = await get_project(db, user.student_no)
    if project is None:
        raise not_found("삭제할 프로젝트가 없습니다")
    cfg = await settings_store.load(db)
    if user.role != Role.admin and cfg.upload_deadline and datetime.now(timezone.utc) > cfg.upload_deadline:
        raise APIError(403, "DEADLINE_PASSED", "마감 후에는 프로젝트를 삭제할 수 없습니다. 선생님께 문의하세요")
    # 빌드 중에는 지우지 않는다. 잠금은 워커가 삭제를 마친 뒤 푼다.
    await acquire_project_lock(user.student_no, "delete")
    audit(db, user, "self_delete", user.student_no)
    await db.commit()
    await enqueue("delete_project", user.student_no)
    return {"ok": True}


# ---- 업로드 ----

async def _check_upload_allowed(db: AsyncSession, user: User) -> None:
    cfg = await settings_store.load(db)
    if user.role != Role.admin and cfg.upload_deadline and datetime.now(timezone.utc) > cfg.upload_deadline:
        raise APIError(403, "DEADLINE_PASSED", "업로드 마감 시간이 지났습니다")
    await rate_limit(f"upload:{user.id}", limit=5, window=600)


def _save(upload: UploadFile, dest: Path, limit: int) -> int:
    size = 0
    with open(dest, "wb") as out:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise upload_invalid(f"파일이 최대 크기({limit // 1024 // 1024}MB)를 넘습니다")
            out.write(chunk)
    return size


async def _create_release(
    db: AsyncSession, user: User, project: Project, rtype: ProjectType, kind: SourceKind,
    ref: str, release_id: uuid.UUID,
) -> Release:
    release = Release(
        id=release_id, project_id=project.id, version=await next_version(db, project),
        type=rtype, source_kind=kind, source_ref=ref, state=ReleaseState.queued,
    )
    db.add(release)
    project.type = rtype
    if project.status in (ProjectStatus.empty, ProjectStatus.failed):
        project.status = ProjectStatus.building
    audit(db, user, "upload", user.student_no)
    await db.commit()
    await enqueue("build_release", str(release.id))
    return release


def _process_upload(file: UploadFile, rtype: ProjectType, rdir: Path) -> tuple[SourceKind, str, list[dict]]:
    s = get_settings()
    name = (file.filename or "").lower()
    limit = s.max_static_bytes if rtype == ProjectType.static else s.max_fullstack_bytes
    warnings: list[dict] = []
    if name.endswith(".html") and rtype == ProjectType.static:
        dest = rdir / "src" / "index.html"
        dest.parent.mkdir()
        _save(file, dest, limit)
        return SourceKind.html, str(dest), v.static_warnings(dest.parent)
    if name.endswith(".zip"):
        dest = rdir / "source.zip"
        _save(file, dest, limit)
        v.safe_extract(dest, rdir / "src", s.max_unpacked_bytes)
        if rtype == ProjectType.static:
            warnings = v.static_warnings(v.find_root(rdir / "src", "index.html"))
        else:
            root = v.find_root(rdir / "src", "docker-compose.yml")
            v.parse_compose((root / "docker-compose.yml").read_text(), root)
        return SourceKind.zip, str(dest), warnings
    raise upload_invalid("zip 파일(정적은 index.html도 가능)을 올려주세요")


@router.post("/releases", status_code=202)
async def upload_release(
    type: ProjectType = Form(...),
    file: UploadFile | None = File(None),
    repo_url: str | None = Form(None),
    branch: str = Form("main"),
    user: User = Depends(mapped_student),
    db: AsyncSession = Depends(get_db),
):
    s = get_settings()
    if type == ProjectType.app:
        raise upload_invalid("앱은 /projects/me/app 으로 올려주세요")
    await _check_upload_allowed(db, user)
    project = await get_or_create_project(db, user)

    release_id = uuid.uuid4()
    await acquire_project_lock(user.student_no, str(release_id))
    rdir = s.releases_dir / str(release_id)
    rdir.mkdir(parents=True, exist_ok=True)
    warnings: list[dict] = []
    try:
        if repo_url:
            if type != ProjectType.fullstack:
                raise upload_invalid("GitHub 저장소는 풀스택 타입에서만 받을 수 있습니다")
            v.check_repo(repo_url.strip(), branch.strip())
            kind, ref = SourceKind.git, f"{repo_url.strip()}@{branch.strip()}"
        elif file is not None and file.filename:
            # 저장·압축 해제·검사는 수백 MB 까지 걸리는 동기 작업이라 스레드에서 돌린다 (다른 요청이 멈추지 않게)
            kind, ref, warnings = await run_in_threadpool(_process_upload, file, type, rdir)
        else:
            raise upload_invalid("파일 또는 GitHub 저장소 주소가 필요합니다")

        release = await _create_release(db, user, project, type, kind, ref, release_id)
    except v.ValidationError as e:
        shutil.rmtree(rdir, ignore_errors=True)
        await release_project_lock(user.student_no)
        raise APIError(400, e.code, e.message, e.detail)
    except BaseException:
        shutil.rmtree(rdir, ignore_errors=True)
        await release_project_lock(user.student_no)
        raise
    return {"release_id": str(release.id), "version": release.version, "warnings": warnings}


@router.post("/app", status_code=202)
async def upload_app(
    title: str = Form(...),
    description: str = Form(""),
    apk: UploadFile = File(...),
    screenshots: list[UploadFile] = File(...),
    user: User = Depends(mapped_student),
    db: AsyncSession = Depends(get_db),
):
    s = get_settings()
    if not 1 <= len(screenshots) <= 5:
        raise upload_invalid("스크린샷은 1~5장이어야 합니다")
    await _check_upload_allowed(db, user)
    project = await get_or_create_project(db, user)

    release_id = uuid.uuid4()
    await acquire_project_lock(user.student_no, str(release_id))
    rdir = s.releases_dir / str(release_id)
    (rdir / "shots").mkdir(parents=True, exist_ok=True)
    try:
        if not (apk.filename or "").lower().endswith(".apk"):
            raise upload_invalid("APK 파일을 올려주세요")
        apk_path = rdir / "app.apk"
        await run_in_threadpool(_save, apk, apk_path, s.max_apk_bytes)
        info = await run_in_threadpool(v.inspect_apk, apk_path)
        for i, shot in enumerate(screenshots):
            data = await shot.read()
            v.check_image(shot.filename or "", len(data), s.max_image_bytes)
            (rdir / "shots" / f"{i + 1}{Path(shot.filename).suffix.lower()}").write_bytes(data)
        (rdir / "meta.json").write_text(
            json.dumps(
                {"title": title.strip()[:100], "description": description.strip()[:2000],
                 "package": info.package, "version_name": info.version_name,
                 "version_code": info.version_code},
                ensure_ascii=False,
            )
        )
        project.title = project.title or title.strip()[:100]
        project.description = project.description or description.strip()[:2000]
        release = await _create_release(db, user, project, ProjectType.app, SourceKind.apk, str(apk_path), release_id)
    except v.ValidationError as e:
        shutil.rmtree(rdir, ignore_errors=True)
        await release_project_lock(user.student_no)
        raise APIError(400, e.code, e.message, e.detail)
    except BaseException:
        shutil.rmtree(rdir, ignore_errors=True)
        await release_project_lock(user.student_no)
        raise
    return {"release_id": str(release.id), "version": release.version, "package": info.package,
            "version_name": info.version_name, "warnings": []}


# ---- 릴리스 ----

@router.get("/releases")
async def my_releases(user: User = Depends(mapped_student), db: AsyncSession = Depends(get_db)):
    project = await get_project(db, user.student_no)
    if project is None:
        return []
    rows = (
        await db.execute(
            select(Release).where(Release.project_id == project.id).order_by(Release.version.desc()).limit(20)
        )
    ).scalars()
    return [release_out(r) for r in rows]


class RollbackIn(BaseModel):
    release_id: uuid.UUID


async def _queue_redeploy(db: AsyncSession, user: User, project: Project, release_id: uuid.UUID, action: str):
    await acquire_project_lock(project.student_no, str(release_id))
    audit(db, user, action, project.student_no)
    await db.commit()
    await enqueue("deploy_existing", str(release_id))


@router.post("/rollback", status_code=202)
async def rollback(body: RollbackIn, user: User = Depends(mapped_student), db: AsyncSession = Depends(get_db)):
    project = await get_project(db, user.student_no)
    release = await db.get(Release, body.release_id)
    if project is None or release is None or release.project_id != project.id:
        raise not_found("릴리스를 찾을 수 없습니다")
    if release.state not in (ReleaseState.active, ReleaseState.superseded):
        raise APIError(400, "UPLOAD_INVALID", "성공했던 릴리스로만 롤백할 수 있습니다")
    await _queue_redeploy(db, user, project, release.id, action="rollback")
    return {"ok": True}


# ---- 중지·기동·로그 ----

async def _require_active(db: AsyncSession, user: User) -> Project:
    project = await get_project(db, user.student_no)
    if project is None or not project.active_release_id:
        raise APIError(400, "NOT_DEPLOYED", "배포된 프로젝트가 없습니다")
    return project


@router.post("/stop", status_code=202)
async def stop(user: User = Depends(mapped_student), db: AsyncSession = Depends(get_db)):
    project = await _require_active(db, user)
    audit(db, user, "stop", project.student_no)
    await db.commit()
    await enqueue("stop_project", project.student_no, "stopped")
    return {"ok": True}


@router.post("/start", status_code=202)
async def start(user: User = Depends(mapped_student), db: AsyncSession = Depends(get_db)):
    project = await _require_active(db, user)
    audit(db, user, "start", project.student_no)
    await db.commit()
    await enqueue("start_project", project.student_no)
    return {"ok": True}


@router.get("/runtime-logs")
async def runtime_logs(
    service: str | None = None, user: User = Depends(mapped_student), db: AsyncSession = Depends(get_db)
):
    project = await _require_active(db, user)
    if service and not re.fullmatch(r"[a-z0-9_-]{1,31}", service):
        raise upload_invalid("서비스 이름이 올바르지 않습니다")
    job = await enqueue("runtime_logs", project.student_no, service)
    try:
        text = await job.result(timeout=25)
    except Exception:
        raise APIError(504, "TIMEOUT", "로그를 가져오지 못했습니다. 잠시 후 다시 시도하세요")
    return {"service": service, "lines": text.splitlines()[-500:]}


# ---- 환경변수 ----

class EnvItem(BaseModel):
    key: str
    value: str | None = None  # 비밀값을 그대로 두려면 null
    secret: bool = False


@router.get("/env")
async def get_env(user: User = Depends(mapped_student), db: AsyncSession = Depends(get_db)):
    project = await get_project(db, user.student_no)
    if project is None:
        return []
    rows = (await db.execute(select(EnvVar).where(EnvVar.project_id == project.id).order_by(EnvVar.key))).scalars()
    return [
        {"key": r.key, "value": None if r.secret else decrypt(r.value_enc), "secret": r.secret}
        for r in rows
    ]


@router.put("/env")
async def put_env(items: list[EnvItem], user: User = Depends(mapped_student), db: AsyncSession = Depends(get_db)):
    if len(items) > 50:
        raise upload_invalid("환경변수는 최대 50개입니다")
    seen = set()
    for item in items:
        if not ENV_KEY_RE.match(item.key):
            raise upload_invalid(f"변수 이름이 올바르지 않습니다: {item.key}")
        if item.key in RESERVED_ENV:
            raise upload_invalid(f"{item.key} 는 플랫폼이 자동으로 넣는 변수입니다")
        if item.key in seen:
            raise upload_invalid(f"중복된 변수: {item.key}")
        seen.add(item.key)
        if item.value is not None and len(item.value) > 4096:
            raise upload_invalid(f"{item.key}: 값이 너무 깁니다")

    project = await get_or_create_project(db, user)
    existing = {
        r.key: r for r in (await db.execute(select(EnvVar).where(EnvVar.project_id == project.id))).scalars()
    }
    for key, row in existing.items():
        if key not in seen:
            await db.delete(row)
    for item in items:
        row = existing.get(item.key)
        if item.value is None:
            if row is None:
                raise upload_invalid(f"{item.key}: 값이 필요합니다")
            row.secret = item.secret
            continue
        if row is None:
            db.add(EnvVar(project_id=project.id, key=item.key, value_enc=encrypt(item.value), secret=item.secret))
        else:
            row.value_enc = encrypt(item.value)
            row.secret = item.secret
    audit(db, user, "env", user.student_no)
    await db.commit()
    return {"ok": True, "note": "다음 배포(또는 재배포)부터 적용됩니다"}
