"""요청 본문을 읽기 전에 돌아야 하는 보안 검사 (순수 ASGI 미들웨어).

FastAPI 는 multipart 본문을 인증 의존성보다 먼저 읽는다. 그래서 여기서 먼저 걸러야
로그인하지 않은 사람이 수백 MB 를 보내 디스크를 채우거나, 학생 페이지가 방문자 쿠키로 요청을 위조하는 걸 막을 수 있다.
"""

import json
from http.cookies import SimpleCookie

from app.config import get_settings
from app.redis_client import redis
from app.security import SESSION_COOKIE
from app.services.agent import ticket_exists

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_HEADER = b"x-s26-request"
VISIT_PATH = "/api/v1/public/visit"
# AI 코딩 도구용. 쿠키 대신 Bearer 토큰·1회용 주소로만 인증하므로 CSRF 헤더 대신 '브라우저에서 온 요청이 아님'을 확인한다
MCP_PATH = "/api/mcp"
AGENT_UPLOAD_PREFIX = "/api/v1/agent/upload/"

# 경로 → 허용 최대 본문 (바이트). 나머지 API 요청은 DEFAULT_MAX.
UPLOAD_LIMITS = {
    "/api/v1/projects/me/releases": 210 * 1024 * 1024,
    "/api/v1/projects/me/app": 290 * 1024 * 1024,  # APK 150 + 영상 100 + 스크린샷 25 + 여유
    "/api/v1/projects/me": 8 * 1024 * 1024,  # 썸네일
    "/api/v1/admin/users/import": 2 * 1024 * 1024,
}
DEFAULT_MAX = 1 * 1024 * 1024
# 로그인해야만 쓸 수 있는 큰 업로드 경로는 본문을 받기 전에 세션부터 확인한다
NEEDS_SESSION = set(UPLOAD_LIMITS)


async def _reject(send, status: int, code: str, message: str) -> None:
    body = json.dumps({"code": code, "message": message, "detail": {}}, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})


class TooLarge(Exception):
    pass


class SecurityGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http" or not scope["path"].startswith("/api/") or scope["method"] not in UNSAFE
            or scope["path"] == VISIT_PATH  # Traefik forwardAuth (본문 없음, 원래 요청 메서드 그대로 옴)
        ):
            return await self.app(scope, receive, send)

        headers = {k.lower(): v for k, v in scope["headers"]}
        path = scope["path"].rstrip("/")

        if path == MCP_PATH or path.startswith(AGENT_UPLOAD_PREFIX):
            return await self._agent(scope, receive, send, headers, path)

        # 1) CSRF: 학생 페이지(science26.bssm.dev)는 같은 사이트라 SameSite 쿠키가 실려 온다.
        #    커스텀 헤더는 다른 출처에서 붙이려면 사전 요청(preflight)이 필요하고, CORS 가 그걸 거절한다.
        site = headers.get(b"sec-fetch-site", b"").decode()
        origin = headers.get(b"origin", b"").decode()
        if CSRF_HEADER not in headers or site not in ("", "same-origin", "none") or (
            origin and origin != get_settings().upload_url
        ):
            return await _reject(send, 403, "FORBIDDEN", "허용되지 않은 출처의 요청입니다")

        # 2) 본문 크기: Content-Length 로 먼저 거르고, 실제로 받는 양도 센다
        limit = UPLOAD_LIMITS.get(path, DEFAULT_MAX)
        length = headers.get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > limit):
            return await _reject(send, 413, "UPLOAD_INVALID", f"요청이 너무 큽니다 (최대 {limit // 1024 // 1024}MB)")

        # 3) 큰 업로드 경로는 세션이 유효할 때만 본문을 받는다
        if path in NEEDS_SESSION:
            cookie = SimpleCookie(headers.get(b"cookie", b"").decode())
            sid = cookie.get(SESSION_COOKIE)
            if sid is None or not await redis.exists(f"sess:{sid.value}"):
                return await _reject(send, 401, "UNAUTHORIZED", "로그인이 필요합니다")

        await self._counted(scope, receive, send, limit)

    async def _agent(self, scope, receive, send, headers, path):
        # 브라우저는 다른 출처로 POST 할 때 Origin 을 꼭 붙인다. CLI 도구(curl, Claude Code 등)는 안 붙인다.
        # 학생 페이지에 심은 스크립트가 1회용 주소나 MCP 를 부르는 것(그리고 DNS 리바인딩)을 막는다.
        if headers.get(b"origin") or headers.get(b"sec-fetch-site"):
            return await _reject(send, 403, "FORBIDDEN", "브라우저에서는 쓸 수 없는 주소입니다")
        if path == MCP_PATH:
            limit = DEFAULT_MAX
        else:
            limit = UPLOAD_LIMITS["/api/v1/projects/me/releases"]
            # 1회용 주소가 살아 있을 때만 본문을 받는다 (아무나 큰 파일을 밀어 넣지 못하게)
            if not await ticket_exists(path[len(AGENT_UPLOAD_PREFIX):]):
                return await _reject(send, 404, "NOT_FOUND", "업로드 주소가 없거나 만료됐어요")
        length = headers.get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > limit):
            return await _reject(send, 413, "UPLOAD_INVALID", f"요청이 너무 큽니다 (최대 {limit // 1024 // 1024}MB)")
        await self._counted(scope, receive, send, limit)

    async def _counted(self, scope, receive, send, limit):
        received = 0

        async def counted_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise TooLarge()
            return message

        try:
            await self.app(scope, counted_receive, send)
        except TooLarge:
            await _reject(send, 413, "UPLOAD_INVALID", f"요청이 너무 큽니다 (최대 {limit // 1024 // 1024}MB)")
