"""학생별 PostgreSQL DB·Redis ACL 계정 발급 (명세 9장 DB·Redis 격리)."""

import asyncpg
from redis.asyncio import Redis

from app.config import get_settings
from app.security import derived_password


def pg_role(student_no: str) -> str:
    return f"stu_{student_no}"


def _pg_dsn() -> str:
    return get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")


async def ensure_postgres(student_no: str) -> str:
    """role·DB가 없으면 만들고, 비밀번호·제한을 매번 맞춘다. DATABASE_URL 을 돌려준다."""
    role = pg_role(student_no)
    password = derived_password("pg", student_no)
    conn = await asyncpg.connect(_pg_dsn())
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role)
        # 식별자는 stu_ + 숫자 4자리로 고정이라 직접 넣어도 안전하다. 비밀번호는 16진수.
        if not exists:
            await conn.execute(f"CREATE ROLE {role} LOGIN PASSWORD '{password}' CONNECTION LIMIT 10")
        else:
            await conn.execute(f"ALTER ROLE {role} LOGIN PASSWORD '{password}' CONNECTION LIMIT 10")
        await conn.execute(f"ALTER ROLE {role} SET statement_timeout = '10s'")
        # 플랫폼 계정이 학생 role 의 DB를 만들고 지울 수 있게 멤버십을 둔다.
        await conn.execute(f"GRANT {role} TO CURRENT_USER")
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", role):
            await conn.execute(f"CREATE DATABASE {role} OWNER {role}")
        await conn.execute(f"REVOKE CONNECT, TEMPORARY ON DATABASE {role} FROM PUBLIC")
        await conn.execute(f"GRANT CONNECT ON DATABASE {role} TO {role}")
    finally:
        await conn.close()
    s = get_settings()
    return f"postgresql://{role}:{password}@{s.student_pg_host}:5432/{role}"


async def drop_postgres(student_no: str) -> None:
    role = pg_role(student_no)
    conn = await asyncpg.connect(_pg_dsn())
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1", role
        )
        await conn.execute(f"DROP DATABASE IF EXISTS {role}")
        await conn.execute(f"DROP ROLE IF EXISTS {role}")
    finally:
        await conn.close()


async def set_db_blocked(student_no: str, blocked: bool) -> None:
    """용량 초과 시 접속을 막고 기존 접속을 끊는다. 다시 줄면 원래 한도(10)로 되돌린다."""
    role = pg_role(student_no)
    conn = await asyncpg.connect(_pg_dsn())
    try:
        await conn.execute(f"ALTER ROLE {role} CONNECTION LIMIT {0 if blocked else 10}")
        if blocked:
            await conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = $1", role
            )
    finally:
        await conn.close()


async def database_sizes() -> dict[str, int]:
    conn = await asyncpg.connect(_pg_dsn())
    try:
        rows = await conn.fetch(
            "SELECT datname, pg_database_size(datname) AS size FROM pg_database WHERE datname LIKE 'stu\\_%'"
        )
    finally:
        await conn.close()
    return {r["datname"].removeprefix("stu_"): r["size"] for r in rows}


def _redis_admin() -> Redis:
    return Redis.from_url(get_settings().student_redis_admin_url, decode_responses=True)


# 주의: 키·채널 패턴을 넣은 뒤에 resetkeys/resetchannels 가 오면 패턴이 지워진다.
# 맨 앞의 reset 이 이미 모두 초기화하므로 여기에는 넣지 않는다.
REDIS_RULES = [
    "-@all",
    "+@read", "+@write", "+@keyspace", "+@string", "+@hash", "+@list", "+@set",
    "+@sortedset", "+@stream", "+@pubsub", "+@transaction", "+@connection", "+@scripting",
    "-@dangerous", "-keys", "-scan", "-flushall", "-flushdb", "-config", "-select", "-swapdb",
]


def redis_acl_args(user: str, password: str) -> list[str]:
    return ["ACL", "SETUSER", user, "reset", "on", f">{password}", f"~{user}:*", f"&{user}:*", *REDIS_RULES]


async def ensure_redis(student_no: str) -> str:
    user = pg_role(student_no)
    password = derived_password("redis", student_no)
    r = _redis_admin()
    try:
        await r.execute_command(*redis_acl_args(user, password))
        await r.execute_command("ACL", "SAVE")
    finally:
        await r.aclose()
    s = get_settings()
    return f"redis://{user}:{password}@{s.student_redis_host}:6379/0"


async def drop_redis(student_no: str) -> None:
    user = pg_role(student_no)
    r = _redis_admin()
    try:
        await r.execute_command("ACL", "DELUSER", user)
        await r.execute_command("ACL", "SAVE")
        async for k in r.scan_iter(match=f"{user}:*", count=500):
            await r.delete(k)
    finally:
        await r.aclose()
