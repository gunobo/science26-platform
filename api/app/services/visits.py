"""학생 페이지 방문자 수. 브라우저 세션 쿠키 하나당, 프로젝트마다 한 번만 센다.

Traefik 이 학생 페이지를 '열 때'(Sec-Fetch-Dest: document)만 /public/visit 으로 forwardAuth 를 보낸다.
학교에서는 한 반이 같은 IP·같은 기종을 쓰므로 IP·User-Agent 대신 쿠키로 구분한다.
"""

import math
import re
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project
from app.redis_client import redis

COOKIE = "__Host-s26v"
COOKIE_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
SLUG_RE = re.compile(r"^/students/([a-z0-9-]{1,32})(?:/|$)")
BOT_RE = re.compile(r"bot|crawl|spider|slurp|preview|monitor|uptime|curl|wget|python|httpx", re.I)
KST = ZoneInfo("Asia/Seoul")

SESSION_SECONDS = 24 * 3600   # 브라우저를 계속 켜 둬도 하루가 지나면 다시 센다
NEW_SESSIONS_PER_IP_HOUR = 30  # 쿠키를 지워 가며 부풀리는 것 방지 (한 반 인원 정도는 넉넉히)


def new_visitor_id() -> str:
    return secrets.token_urlsafe(18)


def valid_visitor_id(value: str | None) -> bool:
    return bool(value and COOKIE_RE.match(value))


def today() -> str:
    return datetime.now(KST).strftime("%Y%m%d")


async def student_no_for(db: AsyncSession, slug: str) -> str | None:
    """링크 이름(또는 학번) → 학번. 페이지마다 DB 를 치지 않게 1분 캐시."""
    cached = await redis.get(f"slugmap:{slug}")
    if cached is not None:
        return cached or None
    no = await db.scalar(select(Project.student_no).where(or_(Project.slug == slug, Project.student_no == slug)))
    await redis.set(f"slugmap:{slug}", no or "", ex=60)
    return no


async def record(student_no: str, visitor_id: str, ip: str, user_agent: str) -> bool:
    """새 방문이면 True. 같은 세션의 재방문·로봇·과도한 새 세션은 세지 않는다."""
    if not user_agent or BOT_RE.search(user_agent):
        return False
    if not await redis.set(f"visited:{student_no}:{visitor_id}", "1", nx=True, ex=SESSION_SECONDS):
        return False
    bucket = f"visitip:{student_no}:{ip}:{datetime.now(KST):%Y%m%d%H}"
    n = await redis.incr(bucket)
    if n == 1:
        await redis.expire(bucket, 3600)
    if n > NEW_SESSIONS_PER_IP_HOUR:
        return False
    day_key = f"visits:{student_no}:day:{today()}"
    pipe = redis.pipeline()
    pipe.incr(f"visits:{student_no}:total")
    pipe.incr(day_key)
    pipe.expire(day_key, 40 * 86400)
    await pipe.execute()
    return True


async def counts(student_nos: list[str]) -> dict[str, dict[str, int]]:
    if not student_nos:
        return {}
    keys = []
    for no in student_nos:
        keys += [f"visits:{no}:total", f"visits:{no}:day:{today()}"]
    vals = await redis.mget(keys)
    return {
        no: {"total": int(vals[2 * i] or 0), "today": int(vals[2 * i + 1] or 0)}
        for i, no in enumerate(student_nos)
    }


# 인기 점수 = Σ (d일 전 방문자 수 × 0.8^d, 최근 14일) + 3 × log₂(1 + 누적 조회수)
# - 오늘 방문은 1배, 하루 지날 때마다 20%씩 덜 쳐 준다 (일주일 전 ≈ 0.21배). 요즘 많이 보는 프로젝트가 위로 온다.
# - 누적 조회수는 로그로 조금만 더한다. 처음에 몰린 조회수만으로 계속 1등을 지키지 못하게.
HOT_DAYS = 14
HOT_DECAY = 0.8
HOT_TOTAL_WEIGHT = 3


def hot_score(daily: list[int], total: int) -> float:
    """daily[d] = d일 전(0 = 오늘) 방문자 수."""
    recent = sum(v * HOT_DECAY**d for d, v in enumerate(daily[:HOT_DAYS]))
    return round(recent + HOT_TOTAL_WEIGHT * math.log2(1 + total), 1)


async def hot_scores(student_nos: list[str]) -> dict[str, float]:
    if not student_nos:
        return {}
    now = datetime.now(KST)
    days = [(now - timedelta(days=d)).strftime("%Y%m%d") for d in range(HOT_DAYS)]
    keys = []
    for no in student_nos:
        keys.append(f"visits:{no}:total")
        keys += [f"visits:{no}:day:{day}" for day in days]
    vals = await redis.mget(keys)
    step = HOT_DAYS + 1
    out = {}
    for i, no in enumerate(student_nos):
        chunk = vals[i * step:(i + 1) * step]
        out[no] = hot_score([int(v or 0) for v in chunk[1:]], int(chunk[0] or 0))
    return out


async def forget(student_no: str) -> None:
    """프로젝트 삭제 시 방문 기록도 지운다."""
    keys = [k async for k in redis.scan_iter(match=f"visits:{student_no}:*")]
    keys += [k async for k in redis.scan_iter(match=f"visited:{student_no}:*")]
    if keys:
        await redis.delete(*keys)
