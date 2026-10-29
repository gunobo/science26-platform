from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.errors import APIError, api_error_handler
from app.middleware import SecurityGuard
from app.routers import admin, agent, auth, me, projects, public

app = FastAPI(title="science26", docs_url="/api/docs", openapi_url="/api/openapi.json")

# 공개 목록 페이지(science26.bssm.dev)가 /public 만 쿠키 없이 부른다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().public_url],
    allow_methods=["GET"],
    allow_credentials=False,
)
app.add_exception_handler(APIError, api_error_handler)
# CSRF·업로드 크기·비로그인 업로드를 본문 파싱 전에 거른다 (가장 바깥에서 실행)
app.add_middleware(SecurityGuard)


@app.exception_handler(RequestValidationError)
async def validation_handler(_, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"code": "UPLOAD_INVALID", "message": "요청 형식이 올바르지 않습니다", "detail": exc.errors()},
    )


for r in (auth.router, me.router, projects.router, public.router, admin.router):
    app.include_router(r, prefix="/api/v1")
# MCP(/api/mcp)와 AI 1회용 업로드(/api/v1/agent/upload/…). 경로를 라우터 안에 직접 적었다
app.include_router(agent.router)


@app.get("/api/health")
async def health():
    return {"ok": True}
