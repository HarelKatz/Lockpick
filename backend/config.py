"""Application configuration via environment variables."""
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: str = os.path.join(os.path.dirname(__file__), "..", "data", "tracker.db")
    upload_path: str = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
    archive_import_max_bytes: int = 100 * 1024 * 1024  # 100 MiB cap on bulk archive uploads


settings = Settings()
