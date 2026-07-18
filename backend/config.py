"""Application configuration via environment variables."""
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: str = os.path.join(os.path.dirname(__file__), "..", "data", "tracker.db")
    upload_path: str = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
    archive_import_max_bytes: int = 100 * 1024 * 1024  # 100 MiB cap on the compressed upload
    archive_import_max_uncompressed_bytes: int = 500 * 1024 * 1024  # 500 MiB cap after extraction (gzip-bomb defense)
    # A single standing rule (an ssh_config Host pattern or an authorized_keys from=
    # ACL) can match a large share of an op — `from="10.0.0.0/8"` on a flat estate
    # matches everything. Past this many matches the rule materializes no edges at
    # all and records a warning instead, rather than burying the graph in a hairball.
    standing_rule_max_matches: int = 25


settings = Settings()
