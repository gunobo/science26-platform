"""AI 연결(MCP) 보안 점검: 토큰 없이·남의 것으로·브라우저에서 못 쓰는지, 1회용 업로드 주소가 정말 한 번만 되는지."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import DeployToken, User
from app.routers import agent as agent_router
from app.services import agent

UPLOAD = get_settings().upload_url
H = {"X-S26-Request": "1", "Origin": UPLOAD}
RAW = agent.TOKEN_PREFIX + "x" * 43


class FakeRedis:
    def __init__(self):
        self.d: dict[str, str] = {}

    async def get(self, k):
        return self.d.get(k)

    async def set(self, k, v, nx=False, ex=None):
        if nx and k in self.d:
            return None
        self.d[k] = str(v)
        return True

    async def exists(self, k):
        return int(k in self.d)

    async def getdel(self, k):
        return self.d.pop(k, None)

    async def incr(self, k):
        self.d[k] = str(int(self.d.get(k, 0)) + 1)
        return int(self.d[k])

    async def expire(self, k, s):
        return True

    async def xrevrange(self, k, count=None):
        return [("2-0", {"kind": "log", "line": "npm run build"}), ("1-0", {"kind": "log", "line": "시작"})]


def make_user(no="1411"):
    return User(id=uuid.uuid4(), email=f"s{no}@bssm.hs.kr", student_no=no, name="학생")


class DB:
    """토큰 해시 → 토큰 행, id → 사용자."""

    def __init__(self, user: User | None, expires_in=timedelta(days=1)):
        self.user = user
        self.token = None
        if user is not None:
            self.token = DeployToken(id=uuid.uuid4(), user_id=user.id, token_hash=agent.hash_token(RAW), prefix=RAW[:10],
                                     expires_at=datetime.now(timezone.utc) + expires_in, last_used_at=None)
        self.queries = []

    async def scalar(self, q):
        self.queries.append(q)
        params = q.compile().params
        if self.token is not None and agent.hash_token(RAW) in params.values():
            return self.token
        return None

    async def get(self, model, key):
        if model is User and self.user is not None and key == self.user.id:
            return self.user
        return None

    async def commit(self): ...
    def add(self, *_): ...


@pytest.fixture
def env(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(agent, "redis", fake)
    monkeypatch.setattr("app.security.redis", fake)
    monkeypatch.setattr(agent_router, "redis", fake)
    state = {"db": DB(make_user()), "started": [], "projects": []}

    async def fake_db():
        yield state["db"]

    async def fake_start(db, user, type, file=None, repo_url=None, branch="main", via=""):
        state["started"].append((user.student_no, type.value, file.filename if file else repo_url, via))
        return {"release_id": "r", "version": 1, "warnings": []}

    async def fake_get_project(db, no):
        state["projects"].append(no)
        return None

    monkeypatch.setattr(agent_router, "start_release", fake_start)
    monkeypatch.setattr(agent_router, "get_project", fake_get_project)
    app.dependency_overrides[get_db] = fake_db
    yield state, fake, TestClient(app)
    app.dependency_overrides.clear()


def rpc(c, method, params=None, token=RAW, headers=None):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return c.post("/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}, headers={**h, **(headers or {})})


# ---- 인증 ----

def test_mcp_requires_valid_token(env):
    state, _, c = env
    r = rpc(c, "tools/list", token=None)
    assert r.status_code == 401 and "Bearer" in r.headers["www-authenticate"]
    assert rpc(c, "tools/list", token="s26_wrong").status_code == 401
    assert rpc(c, "tools/list", token="ghp_notours").status_code == 401
    assert rpc(c, "tools/list").status_code == 200


def test_expired_token_rejected(env):
    state, _, c = env
    state["db"] = DB(make_user(), expires_in=timedelta(seconds=-1))
    assert rpc(c, "tools/list").status_code == 401


def test_unmapped_user_token_rejected(env):
    state, _, c = env
    state["db"] = DB(make_user(no=None))
    assert rpc(c, "tools/list").status_code == 401


def test_session_cookie_is_ignored_by_mcp(env):
    _, _, c = env
    c.cookies.set("s26_session", "whatever")
    c.cookies.set("__Host-s26_session", "whatever")
    assert rpc(c, "tools/list", token=None).status_code == 401


@pytest.mark.parametrize("headers", [{"Origin": "https://science26.bssm.dev"}, {"Origin": UPLOAD}, {"Sec-Fetch-Site": "same-site"}])
def test_mcp_blocks_browsers(env, headers):
    _, _, c = env
    assert rpc(c, "tools/list", headers=headers).status_code == 403


def test_token_cannot_use_session_apis(env):
    """토큰으로 토큰을 더 만들거나 다른 학생 API 를 쓸 수 없다 (쿠키 전용)."""
    _, _, c = env
    auth = {"Authorization": f"Bearer {RAW}"}
    assert c.post("/api/v1/projects/me/tokens", json={}, headers={**H, **auth}).status_code == 401
    assert c.get("/api/v1/projects/me", headers=auth).status_code == 401
    assert c.get("/api/v1/admin/students", headers=auth).status_code == 401


# ---- MCP 프로토콜 ----

def test_initialize_and_list(env):
    _, _, c = env
    r = rpc(c, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
    assert r.json()["result"]["protocolVersion"] == "2025-03-26"
    r = rpc(c, "initialize", {"protocolVersion": "1999-01-01"})
    assert r.json()["result"]["protocolVersion"] == agent_router.PROTOCOL_VERSIONS[0]
    names = {t["name"] for t in rpc(c, "tools/list").json()["result"]["tools"]}
    assert names == {"project_status", "deploy_rules", "create_upload", "deploy_github", "release_status", "rollback"}
    note = c.post("/api/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers={"Authorization": f"Bearer {RAW}"})
    assert note.status_code == 202


def test_bad_json_and_requests(env):
    _, _, c = env
    auth = {"Authorization": f"Bearer {RAW}", "Content-Type": "application/json"}
    assert c.post("/api/mcp", content=b"{not json", headers=auth).json()["error"]["code"] == -32700
    assert c.post("/api/mcp", content=b"[1,2]", headers=auth).json()["error"]["code"] == -32600
    assert rpc(c, "admin/everything").json()["error"]["code"] == -32601
    r = rpc(c, "tools/call", {"name": "delete_everything", "arguments": {}})
    assert r.json()["result"]["isError"]


def test_mcp_body_limit(env):
    _, _, c = env
    big = b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":"' + b"a" * (2 * 1024 * 1024) + b'"}}'
    r = c.post("/api/mcp", content=big, headers={"Authorization": f"Bearer {RAW}", "Content-Type": "application/json"})
    assert r.status_code == 413


def test_tools_only_touch_token_owner_project(env):
    state, _, c = env
    for tool, args in (("project_status", {}), ("release_status", {"version": 1}), ("rollback", {"version": 1}), ("deploy_rules", {})):
        rpc(c, "tools/call", {"name": tool, "arguments": args})
    assert set(state["projects"]) == {"1411"}


@pytest.mark.parametrize("args", [{"type": "app"}, {"type": "../../etc"}, {}])
def test_create_upload_rejects_other_types(env, args):
    _, fake, c = env
    r = rpc(c, "tools/call", {"name": "create_upload", "arguments": args}).json()["result"]
    assert r["isError"] and not any(k.startswith("agentup:") for k in fake.d)


def test_version_must_be_integer(env):
    _, _, c = env
    for bad in ("1 OR 1=1", True, 1.5):
        r = rpc(c, "tools/call", {"name": "release_status", "arguments": {"version": bad}}).json()["result"]
        assert r["isError"]


def test_tool_errors_do_not_leak_as_500(env, monkeypatch):
    from app.errors import APIError

    state, _, c = env

    async def deadline(*a, **k):
        raise APIError(403, "DEADLINE_PASSED", "업로드 마감 시간이 지났습니다")

    monkeypatch.setattr(agent_router, "start_release", deadline)
    r = rpc(c, "tools/call", {"name": "deploy_github", "arguments": {"repo_url": "https://github.com/a/b"}})
    assert r.status_code == 200 and r.json()["result"]["isError"] and "마감" in r.json()["result"]["content"][0]["text"]

    async def boom(*a, **k):
        raise RuntimeError("/opt/science26/secret path")

    monkeypatch.setattr(agent_router, "start_release", boom)
    r = rpc(c, "tools/call", {"name": "deploy_github", "arguments": {"repo_url": "https://github.com/a/b"}})
    assert "/opt" not in r.text and r.json()["result"]["isError"]


# ---- 1회용 업로드 주소 ----

def _ticket(c):
    r = rpc(c, "tools/call", {"name": "create_upload", "arguments": {"type": "static"}}).json()["result"]
    assert not r["isError"]
    import json
    url = json.loads(r["content"][0]["text"])["upload_url"]
    return url[len(UPLOAD):]


def test_upload_ticket_is_one_time_and_bound_to_owner(env):
    state, _, c = env
    path = _ticket(c)
    files = {"file": ("site.zip", b"PK\x03\x04", "application/zip")}
    first = c.post(path, files=files)
    again = c.post(path, files=files)
    assert first.status_code == 202
    assert again.status_code == 404
    assert state["started"] == [("1411", "static", "site.zip", "AI(MCP)")]


def test_upload_ticket_needs_no_token_but_must_exist(env):
    state, _, c = env
    files = {"file": ("site.zip", b"PK", "application/zip")}
    assert c.post("/api/v1/agent/upload/guessed-ticket", files=files).status_code == 404
    assert c.post("/api/v1/agent/upload/" + "a" * 500, files=files).status_code == 404
    assert state["started"] == []


def test_upload_rejects_before_reading_huge_body(env):
    _, _, c = env
    # 주소가 없으면 본문 크기와 상관없이 바로 거절
    r = c.post("/api/v1/agent/upload/nope", content=b"x", headers={"Content-Length": str(10**12)})
    assert r.status_code == 404
    path = _ticket(c)
    r = c.post(path, content=b"x", headers={"Content-Length": str(10**12)})
    assert r.status_code == 413


@pytest.mark.parametrize("headers", [{"Origin": "https://science26.bssm.dev"}, {"Sec-Fetch-Site": "same-site"}])
def test_upload_blocks_browsers(env, headers):
    state, _, c = env
    path = _ticket(c)
    r = c.post(path, files={"file": ("a.zip", b"PK", "application/zip")}, headers=headers)
    assert r.status_code == 403 and state["started"] == []


def test_malformed_content_length_is_not_500(env):
    _, _, c = env
    r = c.post("/api/v1/projects/me", content=b"x", headers={**H, "Content-Length": "12abc"})
    assert r.status_code in (400, 413)


# ---- 토큰 저장 ----

def test_token_is_stored_hashed():
    raw = agent.new_token()
    assert raw.startswith("s26_") and len(raw) > 40
    h = agent.hash_token(raw)
    assert raw not in h and len(h) == 64
    assert agent.new_token() != raw


# ---- 업로드에 섞인 토큰 ----

def test_find_tokens_in_source(tmp_path):
    from app.services.validation import find_tokens

    leaked = agent.new_token()
    (tmp_path / ".mcp.json").write_text('{"headers": {"Authorization": "Bearer ' + leaked + '"}}')
    (tmp_path / "index.html").write_text("<p>s26_short 는 토큰 아님</p>")
    (tmp_path / "big.bin").write_bytes(b"\0" * (6 * 1024 * 1024))
    assert find_tokens(tmp_path) == {leaked}


async def test_live_token_in_upload_stops_deploy_and_revokes(tmp_path, monkeypatch):
    from app import worker
    from app.services import validation as v

    leaked = agent.new_token()
    (tmp_path / "config.js").write_text(f"const t = '{leaked}'")
    revoked = []

    async def fake_revoke(db, tokens):
        revoked.append(tokens)
        return [make_user()]

    class Ctx:
        async def __aenter__(self): return None
        async def __aexit__(self, *a): ...

    monkeypatch.setattr(worker, "SessionLocal", lambda: Ctx())
    monkeypatch.setattr(worker.agent_tokens, "revoke_leaked", fake_revoke)
    logs = []

    async def emit(line): logs.append(line)

    with pytest.raises(v.ValidationError) as e:
        await worker._check_leaked_tokens(tmp_path, emit)
    assert e.value.code == "TOKEN_LEAKED" and leaked not in e.value.message
    assert revoked == [{leaked}]


async def test_dead_token_in_upload_only_warns(tmp_path, monkeypatch):
    from app import worker

    (tmp_path / "a.txt").write_text(agent.new_token())

    async def none_revoked(db, tokens): return []

    class Ctx:
        async def __aenter__(self): return None
        async def __aexit__(self, *a): ...

    monkeypatch.setattr(worker, "SessionLocal", lambda: Ctx())
    monkeypatch.setattr(worker.agent_tokens, "revoke_leaked", none_revoked)
    logs = []

    async def emit(line): logs.append(line)

    await worker._check_leaked_tokens(tmp_path, emit)
    assert any("폐기된 토큰" in l for l in logs)


def test_mcp_instructions_ask_for_gitignore(env):
    _, _, c = env
    text = rpc(c, "initialize", {"protocolVersion": "2025-06-18"}).json()["result"]["instructions"]
    for path in (".mcp.json", ".cursor/mcp.json", ".vscode/mcp.json", ".codex/config.toml", "opencode.json", ".env"):
        assert path in text
    assert ".gitignore" in text
