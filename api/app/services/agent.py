"""AI 코딩 도구(MCP)용 배포 토큰과 1회용 업로드 주소.

- 토큰: 학생이 대시보드에서 만든다. 그 학생 프로젝트 하나만 다룰 수 있고, 관리자 기능은 쓸 수 없다.
  원문은 만들 때 한 번만 보여 주고 DB 에는 SHA-256 만 둔다 (무작위 32바이트라 느린 해시가 필요 없다).
- 업로드 주소: MCP 는 JSON 이라 큰 zip 을 담기 어렵다. 그래서 10분짜리 1회용 주소를 주고 AI 가 curl 로 올린다.
"""

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import APIError
from app.models import DeployToken, User
from app.redis_client import redis
from app.security import rate_limit

TOKEN_PREFIX = "s26_"
TOKEN_DAYS = 30
MAX_TOKENS = 3
TICKET_SECONDS = 600


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def expires() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS)


def token_error(message: str = "AI 연결 토큰이 없거나 만료됐어요. 대시보드에서 새로 만들어 주세요") -> APIError:
    return APIError(401, "UNAUTHORIZED", message)


async def token_user(request: Request, db: AsyncSession) -> User:
    """Authorization: Bearer s26_… → 토큰 주인 (학번이 연결된 학생). 쿠키는 보지 않는다."""
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token.startswith(TOKEN_PREFIX) or len(token) > 100:
        raise token_error()
    row = await db.scalar(select(DeployToken).where(DeployToken.token_hash == hash_token(token)))
    now = datetime.now(timezone.utc)
    if row is None or row.expires_at <= now:
        raise token_error()
    user = await db.get(User, row.user_id)
    if user is None or not user.student_no:
        raise token_error("학번이 연결된 학생 계정만 쓸 수 있어요")
    await rate_limit(f"agent:{user.id}", limit=60, window=60)
    # 마지막 사용 시각은 5분에 한 번만 쓴다
    if row.last_used_at is None or now - row.last_used_at > timedelta(minutes=5):
        row.last_used_at = now
        await db.commit()
    return user


# ---- 1회용 업로드 주소 ----

def _ticket_key(ticket: str) -> str:
    return f"agentup:{ticket}"


async def create_ticket(user: User, project_type: str) -> str:
    ticket = secrets.token_urlsafe(24)
    await redis.set(_ticket_key(ticket), json.dumps({"user_id": str(user.id), "type": project_type}), ex=TICKET_SECONDS)
    return ticket


async def ticket_exists(ticket: str) -> bool:
    return len(ticket) <= 64 and bool(await redis.exists(_ticket_key(ticket)))


async def use_ticket(ticket: str) -> tuple[uuid.UUID, str] | None:
    """한 번 쓰면 사라진다. 동시에 두 번 올려도 하나만 통과한다."""
    raw = await redis.getdel(_ticket_key(ticket)) if len(ticket) <= 64 else None
    if not raw:
        return None
    data = json.loads(raw)
    return uuid.UUID(data["user_id"]), data["type"]
