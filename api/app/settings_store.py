"""관리자가 바꾸는 런타임 설정 (platform_settings 테이블)."""

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PlatformSetting

KEY = "platform"


class PlatformConfig(BaseModel):
    upload_deadline: datetime | None = None
    memory_mb: int = 256
    stack_memory_mb: int = 512
    cpus: float = 0.5
    pids: int = 128
    # 학생 대시보드 위에 뜨는 공지 한 줄 (비우면 안 보임)
    notice: str = ""


async def load(db: AsyncSession) -> PlatformConfig:
    row = await db.get(PlatformSetting, KEY)
    return PlatformConfig.model_validate(row.value) if row else PlatformConfig()


async def save(db: AsyncSession, cfg: PlatformConfig) -> None:
    row = await db.get(PlatformSetting, KEY)
    data = cfg.model_dump(mode="json")
    if row:
        row.value = data
    else:
        db.add(PlatformSetting(key=KEY, value=data))
