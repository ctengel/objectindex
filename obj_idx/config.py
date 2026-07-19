"""Configuration for the ObjectIndex API (pydantic-settings, env-driven).

Environment variables (all prefixed ``OBJIDX_``):

| Variable             | Maps to            | Example                              |
|----------------------|--------------------|--------------------------------------|
| ``OBJIDX_DATABASE_URL`` | ``database_url`` | ``postgresql+psycopg2:///objidx``    |
| ``OBJIDX_S3``        | ``s3``             | ``https://localhost:29164/``         |
| ``OBJIDX_BUCKETS``   | ``buckets``        | ``bucket1,bucket2`` (comma-separated)|
| ``OBJIDX_AUTH_CONFIG`` | ``auth_config``  | ``/etc/objectindex/auth.toml``       |

``OBJIDX_AUTH_CONFIG`` points at a client-key file in the simpler-objects
``auth.toml`` format (``[clients.<name>]`` with ``key`` and per-bucket
``read``/``write``/``list`` permissions); unset means the API is fully open.
"""

from functools import lru_cache
from typing import Annotated, Optional
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from simpler_objects.auth import AuthConfig


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
    auth_config: Optional[str] = None

    @field_validator("buckets", mode="before")
    @classmethod
    def _split_buckets(cls, v):
        """Parse ``OBJIDX_BUCKETS=bucket1,bucket2`` into a list."""
        if isinstance(v, str):
            return [b.strip() for b in v.split(",") if b.strip()]
        return v

    @field_validator("s3")
    @classmethod
    def _reject_s3_credentials(cls, v):
        """Refuse a storage URL with embedded credentials.

        The server only ever echoes this URL back to clients, so embedded
        creds would be nothing but a leak (issue #25).
        """
        parts = urlsplit(v)
        if parts.username or parts.password:
            raise ValueError(
                "OBJIDX_S3 must not embed credentials; clients now "
                "authenticate to simpler-objects directly "
                "(see the 0.4.0 upgrade notes in README.md)")
        return v


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings (cached)."""
    return Settings()


@lru_cache
def get_auth() -> Optional[AuthConfig]:
    """Return the client-key config, or None when auth is off (cached).

    Cached like the settings: edits to the auth.toml need an API restart.
    """
    path = get_settings().auth_config
    return AuthConfig.load(path) if path else None
