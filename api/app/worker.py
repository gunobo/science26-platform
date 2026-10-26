"""arq 워커: 빌드·배포·롤백·중지·슬립·모니터링 (명세 8장)."""

import asyncio
import json
import logging
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import yaml
from arq import cron
from sqlalchemy import select

from app import settings_store
from app.config import get_settings
from app.db import SessionLocal
from app.models import EnvVar, Project, ProjectStatus, ProjectType, Release, ReleaseState, SourceKind
from app.queue import redis_settings, release_project_lock
from app.redis_client import redis
from app.security import decrypt
from app.services import buildlog, docker_ops as d, provision
from app.services import validation as v
from app.services.app_page import build_site
from app.services.compose import (
    STATIC_DOCKERFILE, STATIC_NGINX_CONF, escape_interpolation, network_name, project_name, rewrite,
    static_compose,
)
from app.services.projects import base_path, student_url

log = logging.getLogger("science26.worker")
s = get_settings()


class DeployError(Exception):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


async def notify(message: str) -> None:
    if not s.discord_webhook_url:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(s.discord_webhook_url, json={"content": f"[science26] {message}"[:1900]})
    except Exception:
        log.exception("discord 알림 실패")


# ---- 소스 준비 (validating) ----

def _reject_symlinks(root: Path) -> None:
    for p in root.rglob("*"):
        if p.is_symlink():
            raise v.ValidationError(f"심볼릭 링크는 허용되지 않습니다: {p.relative_to(root)}")


def _dir_size(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


async def prepare_source(release: Release, rdir: Path, emit) -> Path:
    """검증까지 끝난 소스 루트를 돌려준다."""
    src = rdir / "src"
    if release.source_kind == SourceKind.git:
        url, _, branch = release.source_ref.rpartition("@")
        v.check_repo(url, branch)
        shutil.rmtree(src, ignore_errors=True)
        await emit(f"$ git clone --depth 1 --branch {branch} {url}")
        try:
            await d.run(
                "git", "-c", "core.symlinks=false", "clone", "--depth", "1", "--branch", branch,
                "--single-branch", url, str(src), sink=emit, timeout=180,
            )
        except d.CommandError as e:
            raise v.ValidationError(f"저장소를 받을 수 없습니다 (공개 저장소·브랜치 이름 확인)\n{e}")
        shutil.rmtree(src / ".git", ignore_errors=True)
        if _dir_size(src) > s.max_fullstack_bytes:
            raise v.ValidationError("소스가 200MB를 넘습니다")
    elif release.source_kind == SourceKind.zip and not src.exists():
        v.safe_extract(Path(release.source_ref), src, s.max_unpacked_bytes)

    if release.type == ProjectType.app:
        return rdir
    _reject_symlinks(src)
    marker = "index.html" if release.type == ProjectType.static else "docker-compose.yml"
    return v.find_root(src, marker)


# ---- 빌드·배포 ----

async def student_env(db, project: Project) -> dict[str, str]:
    rows = (await db.execute(select(EnvVar).where(EnvVar.project_id == project.id))).scalars()
    return {r.key: decrypt(r.value_enc) for r in rows}


async def compose_for(db, project: Project, release: Release, root: Path, seq: int, emit) -> dict:
    cfg = await settings_store.load(db)
    rdir = s.releases_dir / str(release.id)
    common = dict(
        student_no=project.student_no, slug=project.slug, version=release.version, seq=seq,
        public_host=s.public_host, edge_network=s.edge_network,
    )
    if release.type in (ProjectType.static, ProjectType.app):
        ctx = rdir / "build"
        if not (ctx / "site").exists():
            ctx.mkdir(exist_ok=True)
            if release.type == ProjectType.app:
                build_site(rdir, ctx / "site", student_url(project.slug))
                await emit("앱 소개 페이지 생성 완료")
            else:
                shutil.copytree(root, ctx / "site", ignore=shutil.ignore_patterns("__MACOSX", ".DS_Store"))
                for w in v.static_warnings(root):
                    await emit(f"⚠️ {w['message']} 발견된 경로: {', '.join(w['paths'])}")
            (ctx / "nginx.conf").write_text(STATIC_NGINX_CONF)
            (ctx / "Dockerfile").write_text(STATIC_DOCKERFILE)
        return static_compose(context=ctx, memory_mb=cfg.memory_mb, cpus=cfg.cpus, pids=cfg.pids, **common)

    spec = v.parse_compose((root / "docker-compose.yml").read_text(), root)
    await emit("학생 DB·Redis 계정 확인")
    env = {
        **await student_env(db, project),
        "DATABASE_URL": await _student_db_url(project.student_no),
        "REDIS_URL": await provision.ensure_redis(project.student_no),
        "REDIS_KEY_PREFIX": f"stu_{project.student_no}:",
        "BASE_PATH": base_path(project.slug),
        "PUBLIC_URL": student_url(project.slug).rstrip("/"),
    }
    return rewrite(
        spec, root=root, env=env, memory_mb=cfg.memory_mb, stack_memory_mb=cfg.stack_memory_mb,
        cpus=cfg.cpus, pids=cfg.pids, **common,
    )


async def _student_db_url(student_no: str) -> str:
    url = await provision.ensure_postgres(student_no)
    # ensure_postgres 가 접속 한도를 10 으로 되돌리므로, 용량 초과로 막힌 학생은 다시 막는다
    if await redis.exists(f"dbblocked:{student_no}"):
        await provision.set_db_blocked(student_no, True)
    return url


async def ensure_student_network(student_no: str) -> None:
    net = network_name(student_no)
    try:
        await d.run("docker", "network", "inspect", net)
    except d.CommandError:
        await d.run("docker", "network", "create", net)
    await d.connect_network(net, s.postgres_container, "postgres")
    await d.connect_network(net, s.redis_container, "redis")
    # 예전 버전은 플랫폼 Redis 를 학생 네트워크에 붙였다. 같은 별칭이 둘이면 안 되니 떼어 낸다.
    await d.disconnect_network(net, s.legacy_redis_container)


async def migrate_student_redis() -> None:
    """이미 떠 있는 학생 스택을 학생 전용 Redis 로 옮긴다 (ACL 계정 발급 후 네트워크 별칭 교체).

    플랫폼 Redis 에 있던 학생 데이터는 옮기지 않는다 (학생 Redis 는 캐시 용도로 안내한다).
    """
    for net in await d.list_networks("stu-"):
        m = re.fullmatch(r"stu-(\d{4})-net", net)
        if not m:
            continue
        try:
            await provision.ensure_redis(m.group(1))
            await d.connect_network(net, s.redis_container, "redis")
            await d.disconnect_network(net, s.legacy_redis_container)
        except Exception:
            log.exception("학생 Redis 이전 실패 %s", net)


async def image_total_bytes(spec: dict) -> int:
    """빌드한 이미지 용량 합계. (`docker compose images` 는 컨테이너가 떠 있어야 결과가 나와서 쓰지 않는다)"""
    total = 0
    for svc in spec["services"].values():
        if "build" not in svc:
            continue  # 공식 이미지는 아직 받기 전일 수 있고, 학생이 키울 수 있는 건 빌드 이미지뿐
        try:
            total += int((await d.run("docker", "image", "inspect", "--format", "{{.Size}}", svc["image"])).strip() or 0)
        except (d.CommandError, ValueError):
            pass
    return total


async def healthcheck(slug: str, emit) -> None:
    url = f"{s.traefik_url}{base_path(slug)}/"
    deadline = asyncio.get_event_loop().time() + s.health_timeout_seconds
    last = ""
    async with httpx.AsyncClient(timeout=5, follow_redirects=False) as c:
        while asyncio.get_event_loop().time() < deadline:
            try:
                res = await c.get(url, headers={"Host": s.public_host})
                # 폴백(깨우는 중/준비 중) 페이지는 no-store 헤더가 있어 구분한다
                fallback = res.headers.get("cache-control") == "no-store" and "science26 전체 목록" in res.text
                if 200 <= res.status_code < 400 and not fallback:
                    await emit(f"헬스체크 통과 ({res.status_code})")
                    return
                last = f"HTTP {res.status_code}"
            except httpx.HTTPError as e:
                last = type(e).__name__
            await asyncio.sleep(2)
    raise DeployError(f"헬스체크 실패: {s.health_timeout_seconds}초 안에 {base_path(slug)}/ 가 응답하지 않았습니다 ({last})")


async def deploy(release_id: str, *, build: bool) -> None:
    """build=False 면 이미 빌드된 이미지로 다시 띄운다 (롤백·링크 이름 변경)."""
    async def emit(line: str) -> None:
        await buildlog.append(release_id, line)

    async with SessionLocal() as db:
        release = await db.get(Release, release_id)
        project = await db.get(Project, release.project_id)
        rdir = s.releases_dir / release_id
        pname = project_name(project.student_no, release.version)
        compose_file = rdir / "compose.s26.yml"
        started = False
        prev_active_id = project.active_release_id

        async def set_state(state: ReleaseState) -> None:
            release.state = state
            await db.commit()
            await buildlog.append(release_id, state.value, kind="state")

        try:
            if build:
                await set_state(ReleaseState.validating)
            root = await prepare_source(release, rdir, emit)

            seq = await redis.incr(f"deployseq:{project.student_no}")
            spec = await compose_for(db, project, release, root, seq, emit)
            compose_file.write_text(yaml.safe_dump(escape_interpolation(spec), allow_unicode=True, sort_keys=False))

            if build:
                await set_state(ReleaseState.building)
                await emit(f"$ docker compose build ({pname})")
                await d.run(*d.compose(pname, compose_file, "build", "--pull"), sink=emit, timeout=s.build_timeout_seconds)
                if release.type == ProjectType.fullstack:
                    total = await image_total_bytes(spec)
                    if total > s.max_image_total_bytes:
                        raise DeployError(f"이미지 합계가 2GB를 넘습니다 ({total // 1024 // 1024}MB)")

            await set_state(ReleaseState.deploying)
            if release.type == ProjectType.fullstack:
                await ensure_student_network(project.student_no)
            await emit(f"$ docker compose up -d ({pname})")
            started = True
            await d.run(*d.compose(pname, compose_file, "up", "-d", "--no-build", "--remove-orphans"), sink=emit, timeout=180)
            await healthcheck(project.slug, emit)

            # 성공: 이전 릴리스 superseded, 다른 버전 스택 정리
            if prev_active_id and str(prev_active_id) != release_id:
                prev = await db.get(Release, prev_active_id)
                if prev and prev.state == ReleaseState.active:
                    prev.state = ReleaseState.superseded
            release.state = ReleaseState.active
            release.error = None
            release.finished_at = now()
            project.active_release_id = release.id
            project.status = ProjectStatus.running
            project.last_request_at = now()
            # 뒷정리를 먼저 하고 나서 '서비스 중'으로 바꾼다. 반대로 하면 학생이 완료를 보자마자
            # 다시 올릴 때 아직 잠금이 남아 BUILD_IN_PROGRESS 가 난다.
            # 새 버전은 이미 헬스체크를 통과했으니 뒷정리가 실패해도 배포는 성공으로 둔다.
            try:
                for p in await d.list_projects(f"stu-{project.student_no}-v"):
                    if p["Name"] != pname:
                        await emit(f"이전 스택 정리: {p['Name']}")
                        await d.down_project(p["Name"])
                await prune_releases(db, project)
            except Exception:
                log.exception("배포 뒷정리 실패 %s", pname)
                await emit("⚠️ 이전 버전 정리 중 문제가 있었지만 새 버전은 정상 배포됐어요")
            await db.commit()
            await release_project_lock(project.student_no)
            await buildlog.append(release_id, "active", kind="state")
            await emit(f"✅ 배포 완료: {student_url(project.slug)}")
        except Exception as e:
            msg = e.message if isinstance(e, v.ValidationError) else str(e)
            if not isinstance(e, (v.ValidationError, d.CommandError, DeployError)):
                log.exception("deploy %s 실패", release_id)
                msg = f"내부 오류: {e}"
            await emit(f"❌ {msg}")
            # 새 스택만 내린다. 같은 버전을 다시 띄운 경우(이전 스택과 같은 이름)는 건드리지 않는다.
            if started and (not prev_active_id or str(prev_active_id) != release_id):
                try:
                    await d.down_project(pname)
                except d.CommandError:
                    pass
            await db.rollback()
            release = await db.get(Release, release_id)
            project = await db.get(Project, release.project_id)
            if release.state != ReleaseState.superseded and str(project.active_release_id) != release_id:
                release.state = ReleaseState.failed
                release.error = msg[:4000]
                release.finished_at = now()
            project.status = ProjectStatus.running if project.active_release_id else ProjectStatus.failed
            await db.commit()
            # 새로 올린 버전이 실패하면 소스·빌드 파일과 이미지를 바로 지운다 (롤백 대상이 아니라서 필요 없다).
            # 정리는 성공한 배포 때만 돌기 때문에, 계속 실패하는 업로드가 디스크를 채우지 않게 한다.
            if build and release.state == ReleaseState.failed:
                shutil.rmtree(rdir, ignore_errors=True)
                await d.remove_images(f"s26/stu-{project.student_no}-*:v{release.version}")
        finally:
            await buildlog.end(release_id, release.state.value)
            await release_project_lock(project.student_no)


async def prune_releases(db, project: Project) -> None:
    """최근 릴리스 releases_kept 개만 이미지·파일을 남긴다."""
    rows = (
        await db.execute(
            select(Release).where(Release.project_id == project.id).order_by(Release.version.desc())
        )
    ).scalars().all()
    for r in rows[s.releases_kept:]:
        if r.id == project.active_release_id:
            continue
        await d.remove_images(f"s26/stu-{project.student_no}-*:v{r.version}")
        shutil.rmtree(s.releases_dir / str(r.id), ignore_errors=True)


# ---- 잡 ----

async def build_release(ctx, release_id: str) -> None:
    async with ctx["build_sem"]:
        await deploy(release_id, build=True)


async def deploy_existing(ctx, release_id: str) -> None:
    async with ctx["build_sem"]:
        await deploy(release_id, build=False)


async def _active(db, student_no: str) -> tuple[Project | None, Release | None]:
    project = (await db.execute(select(Project).where(Project.student_no == student_no))).scalar_one_or_none()
    if project is None or not project.active_release_id:
        return project, None
    return project, await db.get(Release, project.active_release_id)


async def stop_project(ctx, student_no: str, status: str = "stopped") -> None:
    async with SessionLocal() as db:
        project, release = await _active(db, student_no)
        if release is None:
            return
        await d.stop_project(project_name(student_no, release.version))
        project.status = ProjectStatus(status)
        await db.commit()


async def start_project(ctx, student_no: str) -> None:
    async with SessionLocal() as db:
        project, release = await _active(db, student_no)
        if release is None:
            return
        pname = project_name(student_no, release.version)
        names = {p["Name"] for p in await d.list_projects(pname)}
        if pname in names:
            if release.type == ProjectType.fullstack:
                await ensure_student_network(student_no)
            await d.start_project(pname)
            project.status = ProjectStatus.running
            project.last_request_at = now()
            await db.commit()
            return
    # 스택이 사라졌으면 (서버 재설치 등) 이미지로 다시 띄운다
    if await redis.set(f"lock:project:{student_no}", "restore", nx=True, ex=1800):
        await deploy(str(release.id), build=False)


async def runtime_logs(ctx, student_no: str, service: str | None) -> str:
    async with SessionLocal() as db:
        _, release = await _active(db, student_no)
        if release is None:
            return ""
    try:
        return await d.logs(project_name(student_no, release.version), service)
    except d.CommandError as e:
        return str(e)


async def delete_project(ctx, student_no: str) -> None:
    try:
        await _delete_project(student_no)
    finally:
        await release_project_lock(student_no)


async def _delete_project(student_no: str) -> None:
    for p in await d.list_projects(f"stu-{student_no}-v"):
        await d.down_project(p["Name"])
    await d.remove_images(f"s26/stu-{student_no}-*")
    await d.remove_network(network_name(student_no))
    await provision.drop_postgres(student_no)
    await provision.drop_redis(student_no)
    async with SessionLocal() as db:
        project = (await db.execute(select(Project).where(Project.student_no == student_no))).scalar_one_or_none()
        if project:
            for r in (await db.execute(select(Release).where(Release.project_id == project.id))).scalars():
                shutil.rmtree(s.releases_dir / str(r.id), ignore_errors=True)
            if project.thumbnail_path:
                Path(project.thumbnail_path).unlink(missing_ok=True)
            await db.delete(project)
            await db.commit()
    await redis.delete(f"stats:{student_no}", f"deployseq:{student_no}")


# ---- 주기 작업 ----

async def prune_build_cache(ctx) -> None:
    await d.prune_build_cache()


_ROUTER_RE = re.compile(r'^traefik_router_requests_total\{[^}]*router="stu-(\d{4})-v\d+(?:-api)?@docker"[^}]*\}\s+([0-9.e+]+)', re.M)


async def track_requests(ctx) -> None:
    """Traefik 라우터 요청 수가 늘어난 학생의 last_request_at 을 갱신한다."""
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            text = (await c.get(s.traefik_metrics_url)).text
    except httpx.HTTPError:
        return
    totals: dict[str, float] = {}
    for no, value in _ROUTER_RE.findall(text):
        totals[no] = totals.get(no, 0) + float(value)
    prev = await redis.hgetall("metrics:requests")
    active = [no for no, total in totals.items() if total != float(prev.get(no, -1))]
    if totals:
        await redis.hset("metrics:requests", mapping={k: str(v_) for k, v_ in totals.items()})
    if active:
        async with SessionLocal() as db:
            for p in (await db.execute(select(Project).where(Project.student_no.in_(active)))).scalars():
                p.last_request_at = now()
            await db.commit()


async def sleep_idle(ctx) -> None:
    """요청이 없는 풀스택 스택을 재운다 (F-12). 정적·앱은 재우지 않는다."""
    cutoff = now() - timedelta(minutes=s.idle_sleep_minutes)
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(Project).where(
                    Project.type == ProjectType.fullstack,
                    Project.status == ProjectStatus.running,
                    Project.last_request_at < cutoff,
                )
            )
        ).scalars().all()
        for project in rows:
            if await redis.exists(f"lock:project:{project.student_no}"):
                continue
            release = await db.get(Release, project.active_release_id)
            if release is None:
                continue
            try:
                await d.stop_project(project_name(project.student_no, release.version))
                project.status = ProjectStatus.sleeping
                await db.commit()
            except d.CommandError:
                log.exception("슬립 실패 %s", project.student_no)


_NAME_RE = re.compile(r"^stu-(\d{4})-v\d+-")


def _mem_bytes(text: str) -> float:
    m = re.match(r"([\d.]+)\s*([KMG]i?B|B)", text.strip())
    if not m:
        return 0
    mult = {"B": 1, "KiB": 1024, "KB": 1000, "MiB": 1024**2, "MB": 1000**2, "GiB": 1024**3, "GB": 1000**3}
    return float(m.group(1)) * mult.get(m.group(2), 1)


async def check_disk() -> None:
    """디스크가 차면 업로드가 막히고(API), 그 전에 관리자에게 알린다."""
    usage = shutil.disk_usage(s.data_dir)
    ratio = usage.used / usage.total
    await redis.set("stats:disk", json.dumps({"used": usage.used, "total": usage.total}), ex=600)
    if ratio >= s.disk_warn_ratio and await redis.set("alerted:disk", "1", nx=True, ex=6 * 3600):
        await notify(
            f"서버 디스크 {ratio:.0%} 사용 중 ({usage.free // 1024 ** 3}GB 남음). "
            f"{s.disk_block_ratio:.0%} 를 넘으면 업로드가 막혀요"
        )


async def collect_stats(ctx) -> None:
    """컨테이너 사용량을 stats:{학번} 에 모아 관리자 대시보드가 읽게 한다. 이상 시 디스코드 알림."""
    try:
        await check_disk()
    except OSError:
        log.exception("디스크 확인 실패")
    try:
        stats = await d.stats()
        containers = await d.ps_labels()
    except d.CommandError:
        return
    agg: dict[str, dict] = {}
    for st in stats:
        m = _NAME_RE.match(st.get("Name", ""))
        if not m:
            continue
        a = agg.setdefault(m.group(1), {"cpu_percent": 0.0, "mem_bytes": 0.0, "containers": 0})
        a["cpu_percent"] += float(st.get("CPUPerc", "0%").rstrip("%") or 0)
        a["mem_bytes"] += _mem_bytes(st.get("MemUsage", "0B").split("/")[0])
        a["containers"] += 1
    try:
        sizes = await provision.database_sizes()
    except Exception:
        sizes = {}
    for no, size in sizes.items():
        agg.setdefault(no, {"cpu_percent": 0.0, "mem_bytes": 0.0, "containers": 0})["db_bytes"] = size
        if size > s.student_db_alert_bytes and await redis.set(f"alerted:db:{no}", "1", nx=True, ex=86400):
            await notify(f"{no} 학생 DB가 {size // 1024 // 1024}MB 입니다 (경고 500MB, 차단 {s.student_db_limit_bytes // 1024 // 1024}MB)")
        # Postgres 에는 DB별 용량 제한이 없어서, 한도를 넘으면 접속을 막아 더 쓰지 못하게 한다.
        # 막힌 동안 학생은 지울 수 없으니, 관리자가 정리해서 한도 아래로 내려가면 자동으로 풀린다.
        blocked = await redis.exists(f"dbblocked:{no}")
        try:
            if size > s.student_db_limit_bytes and not blocked:
                await provision.set_db_blocked(no, True)
                await redis.set(f"dbblocked:{no}", "1")
                await notify(f"{no} 학생 DB가 {size // 1024 // 1024}MB 로 한도를 넘어 접속을 막았어요")
            elif blocked and size <= s.student_db_limit_bytes:
                await provision.set_db_blocked(no, False)
                await redis.delete(f"dbblocked:{no}")
                await notify(f"{no} 학생 DB 용량이 한도 아래로 내려가 접속을 다시 열었어요")
        except Exception:
            log.exception("DB 용량 제한 적용 실패 %s", no)
    for no, a in agg.items():
        await redis.set(f"stats:{no}", json.dumps({**a, "at": now().isoformat()}), ex=600)

    async with SessionLocal() as db:
        running = {
            p.student_no
            for p in (await db.execute(select(Project).where(Project.status == ProjectStatus.running))).scalars()
        }
    for c in containers:
        m = _NAME_RE.match(c.get("Names", ""))
        if m and m.group(1) in running and c.get("State") in ("exited", "dead", "restarting"):
            if await redis.set(f"alerted:ctr:{c['Names']}", "1", nx=True, ex=3600):
                await notify(f"{c['Names']} 컨테이너 상태: {c.get('Status')}")


async def recover_interrupted() -> None:
    """워커가 빌드 도중 꺼졌으면 그 릴리스는 영영 끝나지 않는다. 시작할 때 실패로 정리하고 잠금을 푼다.

    큐에서 기다리던(queued) 잡은 그대로 두고, 실제로 진행 중이던 단계만 정리한다.
    잡 재시도는 max_tries=1 로 막아서 정리한 릴리스가 나중에 다시 돌지 않게 한다.
    """
    in_progress = (ReleaseState.validating, ReleaseState.building, ReleaseState.deploying)
    async with SessionLocal() as db:
        rows = (await db.execute(select(Release).where(Release.state.in_(in_progress)))).scalars().all()
        for release in rows:
            project = await db.get(Project, release.project_id)
            # 서비스 중인 버전을 다시 배포하던 중(롤백·링크 이름 변경)이면 그 스택은 살아 있으니 건드리지 않는다
            if release.id == project.active_release_id:
                release.state = ReleaseState.active
                await db.commit()
                await buildlog.end(str(release.id), "active")
                await release_project_lock(project.student_no)
                continue
            release.state = ReleaseState.failed
            release.error = "워커가 다시 시작되면서 빌드가 중단됐어요. 다시 올려 주세요."
            release.finished_at = now()
            if project.status == ProjectStatus.building:
                project.status = ProjectStatus.running if project.active_release_id else ProjectStatus.failed
            await db.commit()
            try:
                await d.down_project(project_name(project.student_no, release.version))
            except d.CommandError:
                pass
            await buildlog.append(str(release.id), f"❌ {release.error}")
            await buildlog.end(str(release.id), "failed")
            await release_project_lock(project.student_no)
            log.warning("중단된 릴리스 정리: %s v%s", project.student_no, release.version)


async def startup(ctx) -> None:
    logging.basicConfig(level=logging.INFO)
    ctx["build_sem"] = asyncio.Semaphore(s.concurrent_builds)
    s.releases_dir.mkdir(parents=True, exist_ok=True)
    await recover_interrupted()
    await migrate_student_redis()
    # 서버 재부팅 뒤 on-failure 컨테이너는 자동으로 안 뜨므로 running 프로젝트를 다시 켠다.
    async with SessionLocal() as db:
        nos = [
            p.student_no
            for p in (await db.execute(select(Project).where(Project.status == ProjectStatus.running))).scalars()
        ]
    for no in nos:
        try:
            await start_project(ctx, no)
        except Exception:
            log.exception("복구 실패 %s", no)


class WorkerSettings:
    functions = [build_release, deploy_existing, stop_project, start_project, runtime_logs, delete_project]
    cron_jobs = [
        cron(track_requests, second={0, 30}),
        cron(sleep_idle, minute=set(range(0, 60, 2)), second=15),
        cron(collect_stats, minute=set(range(0, 60, 2)), second=45),
        cron(prune_build_cache, hour=4, minute=30),
    ]
    on_startup = startup
    redis_settings = redis_settings()
    max_jobs = 6
    max_tries = 1
    job_timeout = 1800
    keep_result = 60
