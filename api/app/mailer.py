"""관리자 안내 메일 (SMTP).

학교 구글 Workspace·Gmail 이면 smtp.gmail.com:587 + 앱 비밀번호로 보낸다.
API 는 받는 사람별로 내용을 만들어 잡으로 넘기고, 실제 전송은 워커가 한다 (요청이 SMTP 를 기다리지 않게).
진행 상황은 Redis mail:batch:{id} 에 남겨 관리자 화면이 불러 간다.
"""

import html
import json
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.config import get_settings
from app.redis_client import redis

BATCH_TTL = 24 * 3600


def configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_user and s.smtp_password)


def sender() -> str:
    s = get_settings()
    return s.smtp_from or s.smtp_user


def batch_key(batch_id: str) -> str:
    return f"mail:batch:{batch_id}"


async def save_batch(batch_id: str, state: dict) -> None:
    await redis.set(batch_key(batch_id), json.dumps(state, ensure_ascii=False), ex=BATCH_TTL)


async def load_batch(batch_id: str) -> dict | None:
    raw = await redis.get(batch_key(batch_id))
    return json.loads(raw) if raw else None


def _connect() -> smtplib.SMTP:
    s = get_settings()
    if s.smtp_port == 465:
        conn: smtplib.SMTP = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=30, context=ssl.create_default_context())
    else:
        conn = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30)
        conn.starttls(context=ssl.create_default_context())
    conn.login(s.smtp_user, s.smtp_password)
    return conn


class Mailer:
    """연결 하나로 여러 통을 보낸다. 끊기면 한 번 다시 붙는다. 동기 코드라 워커가 스레드에서 부른다."""

    def __init__(self) -> None:
        self.conn: smtplib.SMTP | None = None

    def send(self, to: str, subject: str, body: str, reply_to: str = "", html_body: str = "") -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["From"] = formataddr((s.smtp_from_name, sender()))
        msg["To"] = to
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain=sender().split("@")[-1])
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)
        if html_body:
            msg.add_alternative(html_body, subtype="html")
        for attempt in (1, 2):
            try:
                if self.conn is None:
                    self.conn = _connect()
                self.conn.send_message(msg)
                return
            except (smtplib.SMTPServerDisconnected, ConnectionError, TimeoutError):
                self.close()
                if attempt == 2:
                    raise

    def close(self) -> None:
        if self.conn is not None:
            try:
                self.conn.quit()
            except Exception:
                pass
            self.conn = None


# ---- HTML 메일 ----
# 메일 앱(Gmail·네이버·Outlook)은 <style>·외부 CSS 를 잘 안 읽어서 표(table) + 인라인 스타일로 만든다.

ACCENT = "#047857"
ACCENT_SOFT = "#e3f4ec"
_URL = re.compile(r"https?://[^\s<>\"']+")


def _inline(text: str) -> str:
    """한 줄을 HTML 로: 특수문자 이스케이프 후 주소는 링크로."""
    out, last = [], 0
    for m in _URL.finditer(text):
        out.append(html.escape(text[last:m.start()]))
        url = m.group(0).rstrip(".,)")
        out.append(f'<a href="{html.escape(url)}" style="color:{ACCENT};text-decoration:underline;word-break:break-all">{html.escape(url)}</a>')
        last = m.start() + len(url)
    out.append(html.escape(text[last:]))
    return "".join(out)


def _paragraphs(text: str) -> str:
    """빈 줄로 문단을 나누고, '- ' 로 시작하는 줄은 목록으로."""
    blocks = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.split("\n")
        if all(l.lstrip().startswith(("- ", "• ")) for l in lines):
            items = "".join(
                f'<li style="margin:0 0 6px">{_inline(l.lstrip()[2:])}</li>' for l in lines
            )
            blocks.append(f'<ul style="margin:0 0 16px;padding-left:20px">{items}</ul>')
        else:
            blocks.append(f'<p style="margin:0 0 16px">{"<br>".join(_inline(l) for l in lines)}</p>')
    return "".join(blocks)


def render_html(body: str, *, missing: list[str], button_url: str, button_label: str = "마이페이지에서 바꾸기",
                project_title: str = "", project_url: str = "") -> str:
    font = "-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif"
    checklist = ""
    if missing:
        no_project = missing == ["프로젝트"]
        heading = "아직 프로젝트를 올리지 않았어요" if no_project else "아직 바꾸지 않은 항목"
        rows = "".join(
            f'<tr><td style="padding:4px 0;font-size:14px;color:#1f2937">'
            f'<span style="display:inline-block;width:18px;height:18px;line-height:18px;text-align:center;border-radius:50%;'
            f'background:#fde68a;color:#92400e;font-size:12px;font-weight:700;margin-right:8px">!</span>{html.escape(m)}</td></tr>'
            for m in missing
        )
        title = (
            f'<div style="font-size:13px;color:#4b5563;margin-bottom:6px">'
            + (f'<a href="{html.escape(project_url)}" style="color:#4b5563">{html.escape(project_title)}</a>' if project_url else html.escape(project_title))
            + "</div>"
        ) if project_title else ""
        checklist = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{ACCENT_SOFT};border-radius:12px;margin:0 0 24px">'
            f'<tr><td style="padding:16px 18px">{title}'
            f'<div style="font-size:14px;font-weight:700;color:{ACCENT};margin-bottom:6px">{heading}</div>'
            + (f'<table role="presentation" cellpadding="0" cellspacing="0">{rows}</table>' if not no_project else "")
            + "</td></tr></table>"
        )
    button = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 8px"><tr>'
        f'<td style="border-radius:10px;background:{ACCENT}">'
        f'<a href="{html.escape(button_url)}" style="display:inline-block;padding:13px 22px;font-size:15px;font-weight:700;'
        f'color:#ffffff;text-decoration:none;border-radius:10px">{html.escape(button_label)} →</a></td></tr></table>'
    ) if button_url else ""
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"></head>
<body style="margin:0;padding:0;background:#f3f4f6">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6"><tr><td align="center" style="padding:32px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:16px;overflow:hidden;font-family:{font}">
<tr><td style="background:{ACCENT};padding:20px 28px">
<span style="font-size:18px;font-weight:800;color:#ffffff;letter-spacing:-0.3px">science26</span>
<span style="font-size:13px;color:#d1fae5;margin-left:8px">과학 프로젝트 전시관</span></td></tr>
<tr><td style="padding:28px 28px 8px;font-size:15px;line-height:1.7;color:#1f2937">
{checklist}{_paragraphs(body)}{button}
</td></tr>
<tr><td style="padding:20px 28px 24px;font-size:12px;line-height:1.6;color:#9ca3af;border-top:1px solid #f0f0f0">
이 메일은 science26 관리자가 보냈어요. 궁금한 점은 이 메일에 답장하면 돼요.</td></tr>
</table></td></tr></table></body></html>"""
