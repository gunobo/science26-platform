"""arq 잡 큐 (Redis arq:queue). API는 잡을 넣기만 하고 docker 작업은 전부 워커가 한다."""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import get_settings
from app.errors import APIError
from app.redis_client import redis

_pool: ArqRedis | None = None


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def enqueue(job: str, *args, **kwargs):
    return await (await pool()).enqueue_job(job, *args, **kwargs)


async def claim_runtime_action(student_no: str, seconds: int = 15) -> None:
    """중지·시작 요청이 짧은 시간에 여러 번 들어오면 첫 번째만 받는다 (연속 클릭·중복 요청 방지)."""
    if not await redis.set(f"runtime-action:{student_no}", "1", nx=True, ex=seconds):
        raise APIError(409, "ACTION_IN_PROGRESS", "이미 처리 중이에요. 잠시 후 다시 시도하세요")


def lock_key(student_no: str) -> str:
    return f"lock:project:{student_no}"


async def acquire_project_lock(student_no: str, owner: str, ttl: int = 1800) -> None:
    """동시 배포 방지. 워커가 잡을 끝내면 푼다."""
    if not await redis.set(lock_key(student_no), owner, nx=True, ex=ttl):
        raise APIError(409, "BUILD_IN_PROGRESS", "이미 빌드·배포가 진행 중입니다")


async def release_project_lock(student_no: str) -> None:
    await redis.delete(lock_key(student_no))
