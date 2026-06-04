"""Configuration for the ObjectIndex API (pydantic-settings, env-driven).

Environment variables (all prefixed ``OBJIDX_``):

| Variable             | Maps to            | Example                              |
|----------------------|--------------------|--------------------------------------|
| ``OBJIDX_DATABASE_URL`` | ``database_url`` | ``postgresql+psycopg2:///objidx``    |
| ``OBJIDX_S3``        | ``s3``             | ``http://user:pass@localhost:9000/`` |
| ``OBJIDX_BUCKETS``   | ``buckets``        | ``bucket1,bucket2`` (comma-separated)|
"""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """API settings loaded from the environment / a .env file."""

    model_config = SettingsConfigDict(
        env_prefix="OBJIDX_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str
    s3: str
    # NoDecode keeps pydantic-settings from JSON-decoding the raw env value so
    # the validator below can split a plain comma-separated list.
    buckets: Annotated[list[str], NoDecode]

    @field_validator("buckets", mode="before")
    @classmethod
    def _split_buckets(cls, v):
        """Parse ``OBJIDX_BUCKETS=bucket1,bucket2`` into a list."""
        if isinstance(v, str):
            return [b.strip() for b in v.split(",") if b.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings (cached)."""
    return Settings()
