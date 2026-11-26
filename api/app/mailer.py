"""관리자 안내 메일 (SMTP).

학교 구글 Workspace·Gmail 이면 smtp.gmail.com:587 + 앱 비밀번호로 보낸다.
API 는 받는 사람별로 내용을 만들어 잡으로 넘기고, 실제 전송은 워커가 한다 (요청이 SMTP 를 기다리지 않게).
진행 상황은 Redis mail:batch:{id} 에 남겨 관리자 화면이 불러 간다.
"""

import json
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

    def send(self, to: str, subject: str, body: str, reply_to: str = "") -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["From"] = formataddr((s.smtp_from_name, sender()))
        msg["To"] = to
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain=sender().split("@")[-1])
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body)
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
