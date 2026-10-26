"""빌드 로그: Redis stream buildlog:{release_id} (TTL 1일). SSE 엔드포인트가 이걸 읽는다."""

from app.redis_client import redis

TTL = 24 * 3600
MAXLEN = 5000


def key(release_id) -> str:
    return f"buildlog:{release_id}"


async def append(release_id, line: str, kind: str = "log") -> None:
    k = key(release_id)
    await redis.xadd(k, {"kind": kind, "line": line}, maxlen=MAXLEN, approximate=True)
    await redis.expire(k, TTL)


async def end(release_id, state: str) -> None:
    await append(release_id, state, kind="end")
