"""AI 코딩 도구(Claude Code, Codex, Cursor 등)용 MCP 서버와 1회용 업로드 주소.

MCP 는 Streamable HTTP 의 가장 단순한 형태(상태 없음, POST 하나에 JSON 응답 하나)만 쓴다.
인증은 학생이 만든 배포 토큰(Authorization: Bearer s26_…)으로만 하고 로그인 쿠키는 보지 않는다.
그래서 브라우저가 쿠키를 실어 보내는 CSRF 걱정이 없고, 토큰 주인 학생의 프로젝트 말고는 건드릴 수 없다.
"""

import json
import logging

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings_store
from app.config import get_settings
from app.db import get_db
from app.errors import APIError
from app.models import ProjectType, Release, ReleaseState, User
from app.redis_client import redis
from app.routers.projects import _queue_redeploy, start_release
from app.security import ip_rate_limit
from app.services import agent, buildlog
from app.services import validation as v
from app.services.projects import get_project, project_out, release_out, student_url

log = logging.getLogger(__name__)
router = APIRouter(tags=["agent"])

VIA = "AI(MCP)"
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
RULES_URL = f"{get_settings().public_url}/ai/AGENTS.md"


# ---- 1회용 업로드 주소 ----

@router.post("/api/v1/agent/upload/{ticket}", status_code=202)
async def agent_upload(ticket: str, request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """MCP create_upload 가 준 주소. curl -F file=@build.zip 으로 올린다. 한 번 쓰면 사라진다."""
    await ip_rate_limit(request, "agent-upload", limit=30)
    used = await agent.use_ticket(ticket)
    if used is None:
        raise APIError(404, "NOT_FOUND", "업로드 주소가 없거나 만료됐어요 (10분, 한 번만 쓸 수 있어요). create_upload 를 다시 부르세요")
    user_id, project_type = used
    user = await db.get(User, user_id)
    if user is None or not user.student_no:
        raise agent.token_error("학번이 연결된 학생 계정만 쓸 수 있어요")
    out = await start_release(db, user, ProjectType(project_type), file=file, via=VIA)
    return {**out, "next": "MCP 도구 release_status 로 빌드 결과를 확인하세요"}


# ---- MCP ----

def _text(data) -> dict:
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=1, default=str)
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _tool_error(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}


TOOLS = [
    {
        "name": "project_status",
        "description": "내 science26 프로젝트 상태: 주소, 타입, 실행 상태, 지금 서비스 중인 버전, 마지막 배포 결과, 업로드 마감.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "deploy_rules",
        "description": "science26 에 배포하기 전에 꼭 읽어야 하는 규칙 (경로, 빌드 결과물, docker-compose 제약, 금지 사항). 처음 배포하기 전에 먼저 부르세요.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "create_upload",
        "description": (
            "빌드 결과물(zip, 정적 웹은 index.html 도 가능)을 올릴 1회용 주소와 curl 명령을 만든다. "
            "10분 안에 한 번만 쓸 수 있다. 받은 curl 명령을 터미널에서 실행하면 배포가 시작된다. "
            "모바일 앱(APK)은 지원하지 않으니 대시보드에서 올리게 안내하세요."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"type": {"type": "string", "enum": ["static", "fullstack"], "description": "static = 정적 웹, fullstack = docker compose"}},
            "required": ["type"],
            "additionalProperties": False,
        },
    },
    {
        "name": "deploy_github",
        "description": "공개 GitHub 저장소를 풀스택(docker compose)으로 배포한다. 저장소 루트에 docker-compose.yml 이 있어야 한다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_url": {"type": "string", "description": "https://github.com/아이디/저장소"},
                "branch": {"type": "string", "default": "main"},
            },
            "required": ["repo_url"],
            "additionalProperties": False,
        },
    },
    {
        "name": "release_status",
        "description": "배포 버전의 상태와 빌드 로그 끝부분. 실패했으면 이유가 나온다. version 을 빼면 가장 최근 버전.",
        "inputSchema": {
            "type": "object",
            "properties": {"version": {"type": "integer", "minimum": 1}},
            "additionalProperties": False,
        },
    },
    {
        "name": "rollback",
        "description": "예전에 성공했던 버전으로 되돌린다.",
        "inputSchema": {
            "type": "object",
            "properties": {"version": {"type": "integer", "minimum": 1}},
            "required": ["version"],
            "additionalProperties": False,
        },
    },
]

# 토큰이 든 MCP 설정 파일이 git·업로드에 섞이지 않게
GITIGNORE_LINES = [".mcp.json", ".cursor/mcp.json", ".vscode/mcp.json", ".env", ".env.*"]

INSTRUCTIONS = (
    "science26 학생 프로젝트 배포 서버야. 이 연결은 토큰 주인 학생의 프로젝트 하나만 다룰 수 있어. "
    "가장 먼저, 프로젝트 폴더의 .gitignore 에 다음 줄이 없으면 추가해: " + ", ".join(GITIGNORE_LINES) + ". "
    "이 연결의 토큰(s26_ 로 시작)은 비밀번호야. 코드·커밋·zip·로그 어디에도 넣지 말고, "
    "git commit 이나 zip 을 만들기 전에 s26_ 문자열이 들어간 파일이 없는지 확인해 (서버가 발견하면 배포를 멈추고 토큰을 폐기해). "
    "처음이면 deploy_rules 로 규칙을 읽고, 빌드한 뒤 create_upload 로 받은 curl 명령으로 올리고, "
    "release_status 로 결과를 확인해. 실패하면 로그를 보고 고쳐서 다시 올려. "
    "학생 코드의 의도를 바꾸지 말고 배포에 필요한 부분만 고쳐."
)


async def _tail(release_id, n: int = 60) -> list[str]:
    rows = await redis.xrevrange(buildlog.key(release_id), count=n)
    return [r[1].get("line", "") for r in reversed(rows) if r[1].get("kind") != "end"]


async def _call(name: str, args: dict, user: User, db: AsyncSession) -> dict:
    project = await get_project(db, user.student_no)

    if name == "project_status":
        cfg = await settings_store.load(db)
        if project is None:
            return _text({"student_no": user.student_no, "status": "empty", "message": "아직 올린 적이 없어요",
                          "upload_deadline": cfg.upload_deadline})
        active = await db.get(Release, project.active_release_id) if project.active_release_id else None
        latest = await db.scalar(
            select(Release).where(Release.project_id == project.id).order_by(Release.version.desc()).limit(1)
        )
        out = project_out(project, active, latest)
        out.pop("thumbnail_url", None)
        return _text({**out, "upload_deadline": cfg.upload_deadline})

    if name == "deploy_rules":
        slug = project.slug if project else user.student_no
        return _text(
            f"내 주소: {student_url(slug)} (경로 /students/{slug}/ 아래에서 열림)\n"
            f"전체 규칙은 {RULES_URL} 를 받아서 읽어 (curl -fsSL {RULES_URL}).\n"
            "핵심: 정적 웹은 빌드 결과(index.html 이 있는 폴더)를 zip 으로, 경로는 모두 상대 경로(./)로. "
            "풀스택은 docker-compose.yml 을 루트에 두고 ports 를 쓰지 말고, 웹 서비스는 0.0.0.0 에서 열어. "
            "비밀값은 코드에 넣지 말고 학생이 대시보드 환경변수에 직접 넣게 안내해."
        )

    if name == "create_upload":
        kind = args.get("type")
        if kind not in ("static", "fullstack"):
            return _tool_error("type 은 static 또는 fullstack 이어야 해요")
        ticket = await agent.create_ticket(user, kind)
        url = f"{get_settings().upload_url}/api/v1/agent/upload/{ticket}"
        return _text({
            "upload_url": url,
            "expires_in_seconds": agent.TICKET_SECONDS,
            "curl": f'curl -fsS -F "file=@build.zip" {url}',
            "note": "build.zip 을 실제 파일 경로로 바꿔서 실행해. 정적 웹은 index.html 하나도 돼. 한 번만 쓸 수 있어. "
                    "zip 에 .mcp.json 같은 토큰 설정 파일이 들어가지 않게 해.",
        })

    if name == "deploy_github":
        repo = str(args.get("repo_url", "")).strip()
        branch = str(args.get("branch") or "main").strip()
        out = await start_release(db, user, ProjectType.fullstack, repo_url=repo, branch=branch, via=VIA)
        return _text({**out, "next": "release_status 로 빌드 결과를 확인해"})

    if name in ("release_status", "rollback"):
        if project is None:
            return _tool_error("아직 배포한 적이 없어요")
        q = select(Release).where(Release.project_id == project.id)
        version = args.get("version")
        if version is not None:
            if not isinstance(version, int) or isinstance(version, bool):
                return _tool_error("version 은 숫자여야 해요")
            q = q.where(Release.version == version)
        release = await db.scalar(q.order_by(Release.version.desc()).limit(1))
        if release is None:
            return _tool_error("그 버전을 찾을 수 없어요")
        if name == "rollback":
            if version is None:
                return _tool_error("version 이 필요해요")
            if release.state not in (ReleaseState.active, ReleaseState.superseded):
                return _tool_error("성공했던 버전으로만 되돌릴 수 있어요")
            await _queue_redeploy(db, user, project, release.id, action="rollback")
            return _text({"ok": True, "version": release.version, "next": "release_status 로 확인해"})
        return _text({**release_out(release), "url": student_url(project.slug), "log_tail": await _tail(release.id)})

    return _tool_error(f"없는 도구예요: {name}")


def _rpc(id_, result=None, error=None) -> dict:
    msg = {"jsonrpc": "2.0", "id": id_}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    return msg


@router.api_route("/api/mcp", methods=["GET", "DELETE"], include_in_schema=False)
async def mcp_other():
    # 상태 없는 서버라 서버→클라이언트 스트림(GET)과 세션 종료(DELETE)는 없다
    return Response(status_code=405, headers={"Allow": "POST"})


@router.post("/api/mcp", include_in_schema=False)
async def mcp(request: Request, db: AsyncSession = Depends(get_db)):
    await ip_rate_limit(request, "mcp", limit=600)
    try:
        user = await agent.token_user(request, db)
    except APIError as e:
        return JSONResponse(
            {"code": e.code, "message": e.message}, status_code=e.status,
            headers={"WWW-Authenticate": 'Bearer realm="science26"'} if e.status == 401 else None,
        )
    try:
        msg = json.loads(await request.body())
    except ValueError:
        return JSONResponse(_rpc(None, error={"code": -32700, "message": "Parse error"}), status_code=400)
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return JSONResponse(_rpc(None, error={"code": -32600, "message": "Invalid Request"}), status_code=400)

    method, id_ = msg["method"], msg.get("id")
    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    if id_ is None:  # 알림 (notifications/initialized 등): 응답 없음
        return Response(status_code=202)

    if method == "initialize":
        asked = params.get("protocolVersion")
        return _rpc(id_, {
            "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "science26", "version": "1.0.0"},
            "instructions": INSTRUCTIONS,
        })
    if method == "ping":
        return _rpc(id_, {})
    if method == "tools/list":
        return _rpc(id_, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if not isinstance(name, str):
            return _rpc(id_, error={"code": -32602, "message": "도구 이름이 필요해요"})
        try:
            result = await _call(name, args, user, db)
        except APIError as e:
            # 마감, 디스크, 빌드 중 잠금, 검증 실패 등은 AI 가 읽고 대응할 수 있게 도구 오류로 돌려준다
            result = _tool_error(f"{e.message} ({e.code})")
        except v.ValidationError as e:
            result = _tool_error(e.message)
        except Exception:
            log.exception("MCP 도구 실패: %s", name)
            result = _tool_error("서버 오류가 났어요. 잠시 후 다시 시도하세요")
        return _rpc(id_, result)
    return _rpc(id_, error={"code": -32601, "message": f"Method not found: {method}"})
