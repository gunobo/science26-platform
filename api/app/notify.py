"""디스코드 알림.

- 장애 알림(디스크·DB·컨테이너)은 워커가 send() 를 바로 부른다.
- 활동 알림(첫 접속·프로젝트 등록·수정)은 API 가 activity() 로 기록하고, 전송은 워커 잡에 맡긴다 (요청이 디스코드를 기다리지 않게).
"""

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AuditLog, User
from app.queue import enqueue
from app.redis_client import redis

log = logging.getLogger(__name__)


async def send(message: str, mention: bool = False) -> None:
    s = get_settings()
    if not s.discord_webhook_url:
        return
    users = sorted(s.discord_mention_id_set) if mention else []
    prefix = "".join(f"<@{u}> " for u in users)
    payload = {
        "content": f"{prefix}[science26] {message}"[:1900],
        # 학생이 정한 제목에 @everyone 같은 게 있어도 울리지 않게, 멘션은 지정한 사람만 허용한다
        "allowed_mentions": {"parse": [], "users": users},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(s.discord_webhook_url, json=payload)
    except Exception:
        log.exception("discord 알림 실패")


async def activity(
    db: AsyncSession, actor: User, action: str, message: str, target: str = "", detail: str = "",
    throttle_seconds: int = 0,
) -> None:
    """관리자 대시보드 활동 기록 + 멘션 알림. 커밋은 호출하는 쪽에서 한다.

    throttle_seconds: 같은 사람·같은 종류 알림을 이 시간 동안 한 번만 보낸다 (기록은 매번 남긴다).
    """
    db.add(AuditLog(actor_id=actor.id, action=action, target=target, detail=detail[:500]))
    # E2E 테스트 계정(*@science26.local)은 기록만 하고 멘션은 보내지 않는다
    if actor.email.endswith("@science26.local"):
        return
    if throttle_seconds and not await redis.set(f"notified:{action}:{actor.id}", "1", nx=True, ex=throttle_seconds):
        return
    who = f"{actor.name or actor.email}" + (f" ({actor.student_no})" if actor.student_no else "")
    try:
        await enqueue("send_notification", f"{message}: {who}" + (f"\n{detail}" if detail else ""), True)
    except Exception:
        log.exception("알림 잡 등록 실패")
