from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "WA TODO"
    secret_key: str = Field(default="change-me-in-production")
    database_path: Path = Field(default=Path("data/app.sqlite3"))
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    session_cookie_name: str = "wa_session"
    session_max_age_seconds: int = 60 * 60 * 24 * 7
    session_secure_cookie: bool = True
    session_same_site: str = "lax"

    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 300

    todo_max_length: int = 500
    category_max_length: int = 64

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
