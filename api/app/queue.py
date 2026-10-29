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


def runtime_action_key(student_no: str) -> str:
    return f"runtime-action:{student_no}"


async def claim_runtime_action(student_no: str, seconds: int = 120) -> None:
    """중지·시작이 처리되는 동안 들어온 요청은 거절한다 (연속 클릭·중복 요청 방지).

    워커가 일을 끝내면 바로 풀어 준다 (release_runtime_action). seconds 는 워커가 죽었을 때를 대비한 안전 시간.
    """
    if not await redis.set(runtime_action_key(student_no), "1", nx=True, ex=seconds):
        raise APIError(409, "ACTION_IN_PROGRESS", "이미 처리 중이에요. 잠시 후 다시 시도하세요")


async def release_runtime_action(student_no: str) -> None:
    await redis.delete(runtime_action_key(student_no))


def lock_key(student_no: str) -> str:
    return f"lock:project:{student_no}"


async def acquire_project_lock(student_no: str, owner: str, ttl: int = 1800) -> None:
    """동시 배포 방지. 워커가 잡을 끝내면 푼다."""
    if not await redis.set(lock_key(student_no), owner, nx=True, ex=ttl):
        raise APIError(409, "BUILD_IN_PROGRESS", "이미 빌드·배포가 진행 중입니다")


async def release_project_lock(student_no: str) -> None:
    await redis.delete(lock_key(student_no))
