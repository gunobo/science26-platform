"""운영 서버 E2E 테스트: 테스트 전용 계정으로 실제 공개 주소에 올려 보고 확인한 뒤 정리한다.

서버에서 실행 (워커 이미지 + examples 폴더 마운트):
    docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm \\
      -v ./examples:/examples:ro worker python -m app.e2e [--apk /examples/app.apk] [--keep]

구글 로그인을 거치지 않고 Redis 에 테스트 계정 세션을 직접 만든다. 세션 값은 화면에 출력하지 않는다.
테스트 계정: e2e-test@science26.local, 학번 9999 (실제 학생이 9999 를 쓰면 중단)
"""

import argparse
import asyncio
import base64
import io
import secrets
import sys
import time
import zipfile
from pathlib import Path

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Role, User
from app.redis_client import redis

EMAIL = "e2e-test@science26.local"
STUDENT_NO = "9999"
SLUG = "e2e-test"
STATIC_MARK = "science26-e2e-static"
TERMINAL = {"active", "failed", "superseded"}
# 1x1 PNG (스크린샷 자리)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}", flush=True)
    return ok


async def setup_user() -> str:
    async with SessionLocal() as db:
        holder = (await db.execute(select(User).where(User.student_no == STUDENT_NO))).scalar_one_or_none()
        if holder and holder.email != EMAIL:
            sys.exit(f"학번 {STUDENT_NO} 을 실제 사용자({holder.email})가 쓰고 있어서 중단합니다")
        user = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one_or_none()
        if user is None:
            user = User(email=EMAIL, name="E2E 테스트", student_no=STUDENT_NO, role=Role.student)
            db.add(user)
            await db.commit()
        sid = secrets.token_urlsafe(32)
        await redis.set(f"sess:{sid}", str(user.id), ex=3600)
        return sid


async def teardown_user(sid: str) -> None:
    await redis.delete(f"sess:{sid}")
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one_or_none()
        if user:
            await db.delete(user)
            await db.commit()


def zip_dir(path: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(path.rglob("*")):
            if f.is_file() and "node_modules" not in f.parts:
                zf.write(f, f.relative_to(path))
    return buf.getvalue()


class E2E:
    def __init__(self, sid: str):
        s = get_settings()
        self.upload = s.upload_url
        self.page = f"{s.public_url}/students/{SLUG}/"
        self.api = httpx.AsyncClient(
            base_url=f"{s.upload_url}/api/v1",
            cookies={"s26_session": sid},
            headers={"X-S26-Request": "1", "Origin": s.upload_url},
            timeout=60,
        )
        self.web = httpx.AsyncClient(timeout=30, follow_redirects=True)

    async def close(self):
        await self.api.aclose()
        await self.web.aclose()

    async def wait_release(self, release_id: str, timeout: int) -> dict:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            for r in (await self.api.get("/projects/me/releases")).json():
                if r["id"] == release_id and r["state"] in TERMINAL:
                    return r
            await asyncio.sleep(4)
        return {"state": "timeout", "error": f"{timeout}초 안에 끝나지 않음"}

    async def wait_status(self, want: str, timeout: int = 90) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if (await self.api.get("/projects/me")).json().get("status") == want:
                return True
            await asyncio.sleep(3)
        return False

    async def page_text(self, path: str = "") -> tuple[int, str]:
        r = await self.web.get(self.page + path)
        return r.status_code, r.text

    async def deployed(self, name: str, res: dict) -> bool:
        detail = f"v{res.get('version', '?')} {res['state']}" + (f": {res['error'][:200]}" if res.get("error") else "")
        return record(name, res["state"] == "active", detail)

    # ---- 단계 ----

    async def prepare(self) -> bool:
        me = (await self.api.get("/me")).json()
        if not record("로그인 세션·학번 매핑", me.get("mapped") is True, me.get("email", "")):
            return False
        project = (await self.api.get("/projects/me")).json()
        if project.get("latest_release"):
            await self.delete_project(quiet=True)
        r = await self.api.patch("/projects/me", files={"slug": (None, SLUG), "title": (None, "E2E 테스트"), "listed": (None, "false")})
        return record("링크 이름·정보 수정", r.status_code == 200, r.text[:120] if r.status_code != 200 else "")

    async def csrf(self) -> None:
        bad = await self.web.post(f"{self.upload}/api/v1/projects/me/stop", headers={"Origin": "https://science26.bssm.dev"})
        record("CSRF 차단 (학생 페이지 출처)", bad.status_code == 403, f"HTTP {bad.status_code}")

    async def static(self) -> str | None:
        html = f"<!doctype html><meta charset=utf-8><title>{STATIC_MARK}</title><p>{STATIC_MARK}</p>"
        r = await self.api.post("/projects/me/releases", data={"type": "static"}, files={"file": ("index.html", html.encode(), "text/html")})
        if not record("정적 업로드 접수", r.status_code == 202, r.text[:160] if r.status_code != 202 else ""):
            return None
        rid = r.json()["release_id"]
        if not await self.deployed("정적 배포", await self.wait_release(rid, 240)):
            return None
        code, text = await self.page_text()
        record("정적 페이지 열림", code == 200 and STATIC_MARK in text, f"HTTP {code}")
        return rid

    async def fullstack(self) -> bool:
        src = Path("/examples/fullstack-test")
        if not src.exists():
            return record("풀스택 예제", False, "/examples/fullstack-test 가 없음 (-v ./examples:/examples:ro 확인)")
        r = await self.api.post("/projects/me/releases", data={"type": "fullstack"}, files={"file": ("fullstack.zip", zip_dir(src), "application/zip")})
        if not record("풀스택 업로드 접수", r.status_code == 202, r.text[:160] if r.status_code != 202 else ""):
            return False
        if not await self.deployed("풀스택 빌드·배포", await self.wait_release(r.json()["release_id"], 900)):
            return False
        code, text = await self.page_text()
        record("풀스택 화면 (web 서비스)", code == 200 and "방명록" in text, f"HTTP {code}")
        h = await self.web.get(self.page + "api/health")
        body = h.json() if h.headers.get("content-type", "").startswith("application/json") else {}
        record("API 경로·접두사 제거", h.status_code == 200 and "ok" in body, f"HTTP {h.status_code}")
        record("학생 DB 연결", body.get("db") == "ok", str(body.get("db")))
        record("학생 Redis 연결", body.get("redis") == "ok", str(body.get("redis")))
        record("BASE_PATH 주입", body.get("base") == f"/students/{SLUG}", str(body.get("base")))
        post = await self.web.post(self.page + "api/messages", json={"name": "e2e", "text": "안녕"})
        msgs = (await self.web.get(self.page + "api/messages")).json()
        record("DB 쓰기·읽기", post.status_code == 201 and any(m["text"] == "안녕" for m in msgs))
        r1 = (await self.web.post(self.page + "api/visits")).json()
        r2 = (await self.web.post(self.page + "api/visits")).json()
        if "visits" in r1 and "visits" in r2:
            record("Redis 쓰기 (키 접두사)", r2["visits"] == r1["visits"] + 1, f"{r1['visits']} → {r2['visits']}")
        else:
            record("Redis 쓰기 (키 접두사)", False, str(r2)[:200])
        return True

    async def stop_start(self) -> None:
        await self.api.post("/projects/me/stop")
        stopped = await self.wait_status("stopped")
        code, text = await self.page_text()
        record("중지", stopped and code == 503 and "중지된 프로젝트" in text, f"HTTP {code}")
        await self.api.post("/projects/me/start")
        running = await self.wait_status("running")
        ok = False
        for _ in range(15):
            code, text = await self.page_text()
            if code == 200 and "방명록" in text:
                ok = True
                break
            await asyncio.sleep(3)
        record("다시 시작", running and ok, f"HTTP {code}")
        logs = await self.api.get("/projects/me/runtime-logs", params={"service": "api"})
        record("런타임 로그", logs.status_code == 200 and any("api on :3000" in l for l in logs.json().get("lines", [])))

    async def env(self) -> None:
        r = await self.api.put("/projects/me/env", json=[{"key": "E2E_SECRET", "value": "s3cret", "secret": True}])
        got = (await self.api.get("/projects/me/env")).json()
        record("환경변수 저장·마스킹", r.status_code == 200 and got == [{"key": "E2E_SECRET", "value": None, "secret": True}])

    async def rollback(self, static_id: str) -> None:
        r = await self.api.post("/projects/me/rollback", json={"release_id": static_id})
        if not record("롤백 접수", r.status_code == 202, r.text[:120] if r.status_code != 202 else ""):
            return
        await self.deployed("롤백 배포", await self.wait_release(static_id, 240))
        code, text = await self.page_text()
        record("롤백 후 이전 버전 표시", code == 200 and STATIC_MARK in text, f"HTTP {code}")

    async def app(self, apk: Path) -> None:
        r = await self.api.post(
            "/projects/me/app",
            data={"title": "E2E 앱", "description": "자동 테스트"},
            files=[("apk", (apk.name, apk.read_bytes(), "application/vnd.android.package-archive")),
                   ("screenshots", ("shot.png", PNG, "image/png"))],
        )
        if not record("앱 업로드 접수", r.status_code == 202, r.text[:160]):
            return
        await self.deployed("앱 소개 페이지 배포", await self.wait_release(r.json()["release_id"], 240))
        code, text = await self.page_text()
        record("앱 소개 페이지", code == 200 and "APK 다운로드" in text, f"HTTP {code}")
        a = await self.web.get(self.page + "app.apk")
        record("APK 다운로드", a.status_code == 200 and len(a.content) == apk.stat().st_size, f"HTTP {a.status_code}")

    async def delete_project(self, quiet: bool = False) -> None:
        r = await self.api.delete("/projects/me")
        done = False
        for _ in range(40):
            await asyncio.sleep(3)
            if (await self.api.get("/projects/me")).json().get("latest_release") is None:
                done = True
                break
        if not quiet:
            record("프로젝트 삭제", r.status_code == 202 and done)
            code, _ = await self.page_text()
            record("삭제 후 페이지 사라짐", code == 404, f"HTTP {code}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk", type=Path, help="서명된 APK 경로 (없으면 앱 단계 건너뜀)")
    parser.add_argument("--keep", action="store_true", help="끝나고 테스트 프로젝트·계정을 지우지 않음")
    args = parser.parse_args()

    sid = await setup_user()
    t = E2E(sid)
    try:
        if await t.prepare():
            await t.csrf()
            static_id = await t.static()
            if await t.fullstack():
                await t.env()
                await t.stop_start()
            if static_id:
                await t.rollback(static_id)
            if args.apk:
                if args.apk.exists():
                    await t.app(args.apk)
                else:
                    record("앱", False, f"{args.apk} 없음")
            else:
                print("SKIP  앱 (--apk 로 APK 경로를 주면 테스트)")
    except Exception as e:
        record("예상 못 한 오류", False, f"{type(e).__name__}: {e}")
    finally:
        # 중간에 실패해도 스택·DB 를 남기지 않는다 (계정을 먼저 지우면 주인 없는 스택이 남음)
        if not args.keep:
            try:
                await t.delete_project()
            except Exception as e:
                record("프로젝트 삭제", False, f"{type(e).__name__}: {e}")
        await t.close()
        if not args.keep:
            await teardown_user(sid)
        else:
            await redis.delete(f"sess:{sid}")

    failed = [r for r in results if not r[1]]
    print(f"\n결과: {len(results) - len(failed)}/{len(results)} 통과" + (f", 실패 {len(failed)}개" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
