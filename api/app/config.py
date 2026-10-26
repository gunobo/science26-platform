from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    public_host: str = "science26.bssm.dev"
    upload_host: str = "science26-upload.bssm.dev"

    database_url: str = "postgresql+asyncpg://science26:science26@localhost:5432/science26"
    redis_url: str = "redis://localhost:6379/0"
    data_dir: Path = Path("/data")

    google_client_id: str = ""
    google_client_secret: str = ""
    allowed_google_domains: str = "bssm.hs.kr"
    admin_emails: str = ""
    cookie_secure: bool = True

    secret_key: str = "dev-secret"
    env_encryption_key: str = ""

    discord_webhook_url: str = ""
    # 활동 알림(첫 접속·프로젝트 등록·수정)에서 멘션할 디스코드 사용자 ID, 쉼표로 여러 명
    discord_mention_user_ids: str = ""

    # 학생 스택이 접속하는 공용 인스턴스 (학생 네트워크 안에서의 별칭)
    student_pg_host: str = "postgres"
    student_redis_host: str = "redis"
    postgres_container: str = "s26-postgres"
    # 학생 Redis 는 플랫폼 Redis 와 분리된 인스턴스 (s26-redis 는 예전 버전에서 학생 네트워크에 붙어 있었음)
    redis_container: str = "s26-redis-students"
    legacy_redis_container: str = "s26-redis"
    student_redis_admin_url: str = "redis://localhost:6380/0"
    traefik_url: str = "http://s26-traefik:8000"  # internal 엔트리포인트
    traefik_metrics_url: str = "http://s26-traefik:8082/metrics"
    edge_network: str = "s26-edge"

    # 정책 기본값 (관리자 설정으로 덮어씀)
    session_ttl_seconds: int = 7 * 24 * 3600
    max_static_bytes: int = 100 * 1024 * 1024
    max_fullstack_bytes: int = 200 * 1024 * 1024
    max_apk_bytes: int = 150 * 1024 * 1024
    max_image_bytes: int = 5 * 1024 * 1024
    max_video_bytes: int = 100 * 1024 * 1024
    max_unpacked_bytes: int = 1024 * 1024 * 1024
    max_image_total_bytes: int = 2 * 1024 * 1024 * 1024
    build_timeout_seconds: int = 600
    health_timeout_seconds: int = 60
    idle_sleep_minutes: int = 30
    releases_kept: int = 5
    concurrent_builds: int = 2
    student_db_alert_bytes: int = 500 * 1024 * 1024
    # 이 용량을 넘으면 학생 DB 접속을 막는다 (Postgres 에는 DB별 용량 제한이 없어서)
    student_db_limit_bytes: int = 1024 * 1024 * 1024
    # 디스크 사용률: 경고 알림 / 업로드 차단
    disk_warn_ratio: float = 0.80
    disk_block_ratio: float = 0.90

    @property
    def discord_mention_id_set(self) -> set[str]:
        return {x.strip() for x in self.discord_mention_user_ids.split(",") if x.strip().isdigit()}

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def allowed_domain_set(self) -> set[str]:
        return {d.strip().lower() for d in self.allowed_google_domains.split(",") if d.strip()}

    @property
    def public_url(self) -> str:
        return f"https://{self.public_host}"

    @property
    def upload_url(self) -> str:
        return f"https://{self.upload_host}"

    @property
    def releases_dir(self) -> Path:
        return self.data_dir / "releases"

    @property
    def thumbnails_dir(self) -> Path:
        return self.data_dir / "thumbnails"


@lru_cache
def get_settings() -> Settings:
    return Settings()
