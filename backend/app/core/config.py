from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    postgres_db: str = "employee_portal"
    postgres_user: str = "employee_portal"
    postgres_password: str = Field(min_length=1)
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    seed_admin_password: SecretStr | None = None
    seed_employee_password: SecretStr | None = None

    session_cookie_name: str = "employee_portal_session"
    csrf_cookie_name: str = "employee_portal_csrf"
    session_ttl_hours: int = Field(default=12, gt=0)
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_secure: bool | None = None

    background_check_api_url: str = "https://54capvm12g.execute-api.ap-northeast-2.amazonaws.com"
    background_check_timeout_seconds: float = Field(default=10.0, gt=0)

    @property
    def database_url(self) -> str:
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def use_secure_cookies(self) -> bool:
        if self.cookie_samesite == "none":
            return True
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.app_env.lower() not in {"development", "test"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
