from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LESS_", env_file=ROOT / ".env", extra="ignore")

    database_url: str = f"sqlite:///{ROOT / 'data' / 'less.db'}"
    timezone: str = "Asia/Shanghai"
    agent_provider: Literal["auto", "codex", "antigravity"] = "auto"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    mail_from: str = ""
    mail_to: str = ""

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


@lru_cache
def settings() -> Settings:
    return Settings()
