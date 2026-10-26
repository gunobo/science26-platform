from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services import validation as v
from app.services.compose import rewrite, static_compose

H = {"X-S26-Request": "1"}
UPLOAD = get_settings().upload_url


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_get_is_not_blocked(client):
    assert client.get("/api/health").status_code == 200


def test_unsafe_without_csrf_header_rejected(client):
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 403


@pytest.mark.parametrize("headers", [
    {"Origin": "https://science26.bssm.dev"},          # 학생 페이지 출처
    {"Sec-Fetch-Site": "same-site"},                    # 같은 사이트의 다른 출처
    {"Sec-Fetch-Site": "cross-site"},
    {"Origin": "https://evil.example"},
])
def test_cross_origin_rejected_even_with_header(client, headers):
    assert client.post("/api/v1/auth/logout", headers={**H, **headers}).status_code == 403


def test_same_origin_with_header_passes(client):
    r = client.post("/api/v1/auth/logout", headers={**H, "Origin": UPLOAD, "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200


def test_oversized_body_rejected_before_reading(client):
    r = client.post("/api/v1/projects/me/releases", headers={**H, "Content-Length": str(500 * 1024 * 1024)}, content=b"")
    assert r.status_code == 413


def test_small_api_body_limit(client):
    r = client.post("/api/v1/auth/logout", headers=H, content=b"x" * (2 * 1024 * 1024))
    assert r.status_code == 413


def test_upload_without_session_rejected_before_body(client):
    r = client.post("/api/v1/projects/me/releases", headers=H, files={"file": ("a.zip", b"x" * 1000)}, data={"type": "static"})
    assert r.status_code == 401


def _project(tmp_path: Path, compose: dict) -> Path:
    import yaml
    (tmp_path / "docker-compose.yml").write_text(yaml.safe_dump(compose))
    return tmp_path


def test_student_labels_whitelisted(tmp_path):
    compose = {"services": {"web": {"image": "nginx", "labels": {
        "science26.public": "true", "science26.port": "8080",
        "com.docker.compose.project": "stu-9999-v1", "traefik.enable": "true", "anything": "x"}}}}
    root = _project(tmp_path, compose)
    spec = v.parse_compose((root / "docker-compose.yml").read_text(), root)
    out = rewrite(spec, root=root, student_no="1411", slug="x", version=1, seq=1, env={},
                  public_host="h", edge_network="e", memory_mb=256, stack_memory_mb=512, cpus=0.5, pids=128)
    labels = out["services"]["web"]["labels"]
    assert "com.docker.compose.project" not in labels and "anything" not in labels
    assert labels["science26.port"] == "8080"


def test_student_containers_have_log_limits(tmp_path):
    out = static_compose(student_no="1411", slug="x", version=1, seq=1, context=tmp_path,
                         public_host="h", edge_network="e", memory_mb=256, cpus=0.5, pids=128)
    assert out["services"]["web"]["logging"]["options"]["max-size"] == "5m"


def test_login_rate_limited_per_ip(client, monkeypatch):
    from app import security

    counts: dict[str, int] = {}

    async def fake_rate_limit(key, limit, window):
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > limit:
            raise security.APIError(429, "RATE_LIMITED", "too many")

    monkeypatch.setattr(security, "rate_limit", fake_rate_limit)
    monkeypatch.setattr("app.routers.auth.redis.set", lambda *a, **k: _noop())
    statuses = [client.get("/api/v1/auth/google/login", follow_redirects=False).status_code for _ in range(302)]
    assert statuses[0] == 307 and statuses[299] == 307 and statuses[-1] == 429


async def _noop():
    return True


def test_upload_blocked_when_disk_full(client, monkeypatch):
    import shutil
    from collections import namedtuple

    from app.routers import projects

    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda _: Usage(100, 95, 5))
    import asyncio
    with pytest.raises(projects.APIError) as e:
        asyncio.run(projects._check_upload_allowed(None, None))
    assert e.value.status == 507


def test_session_cookie_uses_host_prefix_in_production():
    from app.security import SESSION_COOKIE

    # 기본 설정(cookie_secure=True)에서는 하위 도메인이 덮어쓸 수 없는 __Host- 쿠키
    assert SESSION_COOKIE == "__Host-s26_session"


def test_traefik_dynamic_file_strips_service_worker_allowed():
    import yaml
    from pathlib import Path

    conf = yaml.safe_load((Path(__file__).parents[2] / "infra/traefik/dynamic/students.yml").read_text())
    hdr = conf["http"]["middlewares"]["student-response-headers"]["headers"]["customResponseHeaders"]
    assert hdr == {"Service-Worker-Allowed": ""}


def test_discord_mentions_only_configured_users(monkeypatch):
    import asyncio

    from app import notify

    sent = {}

    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): ...
        async def post(self, url, json): sent.update(json)

    s = get_settings()
    monkeypatch.setattr(s, "discord_webhook_url", "https://discord.example/hook")
    monkeypatch.setattr(s, "discord_mention_user_ids", "945179735003127851, x")
    monkeypatch.setattr(notify.httpx, "AsyncClient", FakeClient)

    asyncio.run(notify.send("프로젝트 등록: @everyone 학생", mention=True))
    assert sent["content"].startswith("<@945179735003127851> [science26]")
    assert sent["allowed_mentions"] == {"parse": [], "users": ["945179735003127851"]}

    asyncio.run(notify.send("디스크 경고"))
    assert sent["allowed_mentions"] == {"parse": [], "users": []} and "<@" not in sent["content"]
