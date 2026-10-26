"""docker CLI 래퍼. 워커에서만 쓴다 (DOCKER_HOST=docker-socket-proxy)."""

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path

LineSink = Callable[[str], Awaitable[None]]


class CommandError(Exception):
    pass


# 워커 프로세스 환경에는 DB·Redis 관리자 비밀번호, SECRET_KEY 가 있다.
# docker·git 에는 동작에 필요한 것만 넘겨서, 학생 파일이 어떤 식으로든 이 값을 읽지 못하게 한다.
_PASS_ENV = ("PATH", "HOME", "DOCKER_HOST", "DOCKER_BUILDKIT", "LANG", "TZ")


def clean_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _PASS_ENV if k in os.environ}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


async def run(
    *args: str, sink: LineSink | None = None, timeout: float | None = None, cwd: Path | None = None
) -> str:
    """명령을 돌리고 stdout+stderr 를 줄 단위로 sink 에 흘린다. 실패하면 마지막 몇 줄로 CommandError."""
    proc = await asyncio.create_subprocess_exec(
        *args, cwd=cwd, env=clean_env(), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    lines: list[str] = []

    async def pump():
        assert proc.stdout
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            lines.append(line)
            if sink:
                await sink(line)

    try:
        await asyncio.wait_for(asyncio.gather(pump(), proc.wait()), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise CommandError(f"시간 초과 ({int(timeout or 0)}초)")
    if proc.returncode != 0:
        tail = "\n".join(lines[-15:])
        raise CommandError(f"{args[0]} {args[1] if len(args) > 1 else ''} 실패 (exit {proc.returncode})\n{tail}")
    return "\n".join(lines)


def compose(project: str, file: Path, *args: str) -> tuple[str, ...]:
    return ("docker", "compose", "-p", project, "-f", str(file), *args)


async def list_projects(prefix: str) -> list[dict]:
    """docker compose ls (중지된 것 포함) 중 이름이 prefix 로 시작하는 것."""
    out = await run("docker", "compose", "ls", "-a", "--format", "json")
    return [p for p in json.loads(out or "[]") if p["Name"].startswith(prefix)]


async def down_project(project: str) -> None:
    await run("docker", "compose", "-p", project, "down", "--remove-orphans", "--timeout", "10")


async def stop_project(project: str) -> None:
    await run("docker", "compose", "-p", project, "stop", "--timeout", "10")


async def start_project(project: str) -> None:
    await run("docker", "compose", "-p", project, "start")


async def logs(project: str, service: str | None, tail: int = 500) -> str:
    args = ["docker", "compose", "-p", project, "logs", "--no-color", "--no-log-prefix", "--tail", str(tail)]
    if service:
        args.append(service)
    return await run(*args, timeout=20)


async def connect_network(network: str, container: str, alias: str) -> None:
    try:
        await run("docker", "network", "connect", "--alias", alias, network, container)
    except CommandError as e:
        if "already exists" not in str(e):
            raise


async def disconnect_network(network: str, container: str) -> None:
    try:
        await run("docker", "network", "disconnect", "-f", network, container)
    except CommandError:
        pass


async def list_networks(prefix: str) -> list[str]:
    out = await run("docker", "network", "ls", "--filter", f"name={prefix}", "--format", "{{.Name}}")
    return [n for n in out.split() if n.startswith(prefix)]


async def prune_build_cache() -> None:
    """3일 지난 빌드 캐시와 이름 없는 이미지를 지운다."""
    for args in (("docker", "buildx", "prune", "-f", "--filter", "until=72h"), ("docker", "image", "prune", "-f")):
        try:
            await run(*args, timeout=600)
        except CommandError:
            pass


async def remove_network(network: str) -> None:
    try:
        await run("docker", "network", "rm", network)
    except CommandError:
        pass


async def remove_images(reference: str) -> None:
    """reference 필터에 맞는 이미지를 지운다 (예: s26/stu-1411-*:v3)."""
    out = await run("docker", "images", "--filter", f"reference={reference}", "--format", "{{.ID}}")
    ids = sorted(set(out.split()))
    if ids:
        try:
            await run("docker", "rmi", "-f", *ids)
        except CommandError:
            pass


async def stats() -> list[dict]:
    out = await run("docker", "stats", "--no-stream", "--format", "{{json .}}", timeout=60)
    return [json.loads(line) for line in out.splitlines() if line.strip()]


async def ps_labels() -> list[dict]:
    out = await run(
        "docker", "ps", "-a", "--filter", "label=science26.student", "--format", "{{json .}}", timeout=30
    )
    return [json.loads(line) for line in out.splitlines() if line.strip()]
