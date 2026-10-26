import hashlib
import hmac
import secrets
import time
import uuid

from cryptography.fernet import Fernet
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.errors import APIError, forbidden, unauthorized
from app.models import AuditLog, Role, User
from app.redis_client import redis

SESSION_COOKIE = "s26_session"


# ---- 세션 ----

async def create_session(user_id: uuid.UUID) -> str:
    sid = secrets.token_urlsafe(32)
    await redis.set(f"sess:{sid}", str(user_id), ex=get_settings().session_ttl_seconds)
    return sid


async def delete_session(sid: str) -> None:
    await redis.delete(f"sess:{sid}")


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        raise unauthorized()
    user_id = await redis.get(f"sess:{sid}")
    if not user_id:
        raise unauthorized()
    user = await db.get(User, uuid.UUID(user_id))
    if user is None:
        raise unauthorized()
    await rate_limit(f"api:{user.id}", limit=60, window=60)
    return user


async def mapped_student(user: User = Depends(current_user)) -> User:
    """학번이 매핑된 사용자만. 관리자도 학번이 있으면 학생 기능을 쓸 수 있다."""
    if not user.student_no:
        raise APIError(403, "NOT_MAPPED", "학번 매핑 대기 중입니다. 선생님께 문의하세요")
    return user


async def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != Role.admin:
        raise forbidden()
    return user


# ---- rate limit (고정 윈도) ----

async def rate_limit(key: str, limit: int, window: int) -> None:
    bucket = f"rl:{key}:{int(time.time()) // window}"
    count = await redis.incr(bucket)
    if count == 1:
        await redis.expire(bucket, window)
    if count > limit:
        raise APIError(429, "RATE_LIMITED", "요청이 너무 많습니다. 잠시 후 다시 시도하세요")


# ---- 암호화·파생 비밀번호 ----

def fernet() -> Fernet:
    key = get_settings().env_encryption_key
    if not key:
        raise RuntimeError("ENV_ENCRYPTION_KEY 가 설정되지 않았습니다")
    return Fernet(key.encode())


def encrypt(value: str) -> bytes:
    return fernet().encrypt(value.encode())


def decrypt(value: bytes) -> str:
    return fernet().decrypt(value).decode()


def derived_password(purpose: str, student_no: str) -> str:
    """학생 DB·Redis 비밀번호. 저장하지 않고 SECRET_KEY에서 매번 같은 값을 만든다."""
    digest = hmac.new(
        get_settings().secret_key.encode(), f"{purpose}:{student_no}".encode(), hashlib.sha256
    )
    return digest.hexdigest()[:32]


# ---- 감사 로그 ----

def audit(db: AsyncSession, actor: User | None, action: str, target: str = "") -> None:
    db.add(AuditLog(actor_id=actor.id if actor else None, action=action, target=target))
