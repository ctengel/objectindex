"""Configuration for the ObjectIndex API (pydantic-settings, env-driven).

Environment variables (all prefixed ``OBJIDX_``):

| Variable             | Maps to            | Example                              |
|----------------------|--------------------|--------------------------------------|
| ``OBJIDX_DATABASE_URL`` | ``database_url`` | ``postgresql+psycopg2:///objidx``    |
| ``OBJIDX_S3``        | ``s3``             | ``http://user:pass@localhost:9000/`` |
| ``OBJIDX_BUCKETS``   | ``buckets``        | ``["bucket1"]`` (JSON list)          |
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """API settings loaded from the environment / a .env file."""

    model_config = SettingsConfigDict(
        env_prefix="OBJIDX_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str
    s3: str
    buckets: list[str]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings (cached)."""
    return Settings()
