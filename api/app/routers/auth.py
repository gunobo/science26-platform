import base64
import json
import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.errors import APIError, forbidden
from app.models import Role, User
from app.redis_client import redis
from app.security import SESSION_COOKIE, create_session, delete_session

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"


def is_allowed(email: str, hd: str | None) -> bool:
    """학교 Workspace 계정(hd 클레임) 또는 ADMIN_EMAILS 에 있는 계정만 통과."""
    s = get_settings()
    return (hd or "").lower() in s.allowed_domain_set or email.lower() in s.admin_email_set


def _redirect_uri() -> str:
    return f"{get_settings().upload_url}/api/v1/auth/google/callback"


def _set_session_cookie(response, sid: str) -> None:
    s = get_settings()
    # Domain 속성을 빼서 upload 호스트 전용 쿠키로 둔다 (학생 페이지 오리진에 노출되지 않음).
    response.set_cookie(
        SESSION_COOKIE,
        sid,
        max_age=s.session_ttl_seconds,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


async def _login_as(db: AsyncSession, email: str, name: str) -> User:
    s = get_settings()
    email = email.lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        user = User(email=email, name=name)
        db.add(user)
    if not user.name:
        user.name = name
    user.role = Role.admin if email in s.admin_email_set else Role.student
    await db.commit()
    return user


@router.get("/google/login")
async def google_login():
    s = get_settings()
    state = secrets.token_urlsafe(24)
    await redis.set(f"oauth:{state}", "1", ex=600)
    params = {
        "client_id": s.google_client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    # 관리자 중 학교 밖 계정(예: 개인 Gmail)이 있으면 hd 힌트를 빼야 계정 선택 화면에서 고를 수 있다
    if len(s.allowed_domain_set) == 1 and all(
        e.rsplit("@", 1)[-1] in s.allowed_domain_set for e in s.admin_email_set
    ):
        params["hd"] = next(iter(s.allowed_domain_set))
    return RedirectResponse(f"{GOOGLE_AUTH}?{urlencode(params)}")


def _decode_id_token(token: str) -> dict:
    # 토큰 엔드포인트에서 TLS로 직접 받은 id_token이라 서명 검증 대신 클레임만 확인한다.
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


@router.get("/google/callback")
async def google_callback(
    code: str = "", state: str = "", error: str = "", db: AsyncSession = Depends(get_db)
):
    s = get_settings()
    if error or not code or not await redis.getdel(f"oauth:{state}"):
        return RedirectResponse("/?error=oauth")

    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(
            GOOGLE_TOKEN,
            data={
                "code": code,
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
                "redirect_uri": _redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
    if res.status_code != 200:
        return RedirectResponse("/?error=oauth")
    claims = _decode_id_token(res.json()["id_token"])

    if claims.get("aud") != s.google_client_id or claims.get("iss") not in (
        "accounts.google.com",
        "https://accounts.google.com",
    ):
        return RedirectResponse("/?error=oauth")
    if not claims.get("email_verified") or not is_allowed(claims.get("email", ""), claims.get("hd")):
        return RedirectResponse("/?error=domain")

    user = await _login_as(db, claims["email"], claims.get("name", ""))
    sid = await create_session(user.id)
    response = RedirectResponse("/")
    _set_session_cookie(response, sid)
    return response


class DevLogin(BaseModel):
    email: str
    name: str = ""


@router.post("/dev-login")
async def dev_login(body: DevLogin, db: AsyncSession = Depends(get_db)):
    """로컬 개발 전용. DEV_LOGIN=true 일 때만 열린다."""
    if os.environ.get("DEV_LOGIN") != "true":
        raise forbidden()
    if not is_allowed(body.email, body.email.rsplit("@", 1)[-1]):
        raise APIError(403, "FORBIDDEN", "학교 계정만 로그인할 수 있습니다")
    user = await _login_as(db, body.email, body.name)
    sid = await create_session(user.id)
    response = JSONResponse({"ok": True})
    _set_session_cookie(response, sid)
    return response


@router.post("/logout")
async def logout(request: Request):
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        await delete_session(sid)
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
