"""FastAPI service settings. Loaded from env via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime config for the FastAPI service."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "prosperity"
    platform_api_key: str = "change-me"
    storage_root: Path = Path("storage")

    @property
    def datasets_dir(self) -> Path:
        return self.storage_root / "data"

    @property
    def strategies_dir(self) -> Path:
        return self.storage_root / "strategies"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
