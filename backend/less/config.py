from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LESS_", env_file=ROOT / ".env", extra="ignore")
    database_url: str = "postgresql+psycopg://less:less_local@127.0.0.1:55432/less"
    redis_url: str = "redis://127.0.0.1:56379/0"
    data_dir: Path = ROOT / "data"
    codex_bin: str = "codex"
    codex_model: str = ""
    codex_timeout: int = Field(default=180, ge=10, le=1800)
    max_items_per_check: int = Field(default=5, ge=1, le=50)
    auto_normalize: bool = False
    ai_daily_limit: int = Field(default=10, ge=1, le=200)
    timezone: str = "Asia/Shanghai"
    max_attempts: int = 3

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        ZoneInfo(value)
        return value


@lru_cache
def settings() -> Settings:
    return Settings()
