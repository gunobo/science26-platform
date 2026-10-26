from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, detail: Any = None):
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail or {}


def unauthorized() -> APIError:
    return APIError(401, "UNAUTHORIZED", "로그인이 필요합니다")


def forbidden(message: str = "권한이 없습니다") -> APIError:
    return APIError(403, "FORBIDDEN", message)


def not_found(message: str = "찾을 수 없습니다") -> APIError:
    return APIError(404, "NOT_FOUND", message)


def upload_invalid(message: str, detail: Any = None) -> APIError:
    return APIError(400, "UPLOAD_INVALID", message, detail)


async def api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content={"code": exc.code, "message": exc.message, "detail": exc.detail},
    )
