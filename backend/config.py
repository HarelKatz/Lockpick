"""Application configuration via environment variables."""
import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_path: str = os.path.join(os.path.dirname(__file__), "..", "data", "tracker.db")
    upload_path: str = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")

    class Config:
        env_file = ".env"


settings = Settings()
