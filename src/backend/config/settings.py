"""Application settings loaded from environment variables.

All configuration is read from the environment (or a .env file via pydantic-settings).
No secrets or connection strings are hardcoded here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object for the application.

    Values are read from environment variables (case-insensitive).
    A .env file in the project root is also supported.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_name: str = Field(default="Backend API", description="Human-readable application name.")
    debug: bool = Field(default=False, description="Enable debug mode.")

    # ------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------
    database_url: str = Field(
        ...,
        description="Async SQLAlchemy database URL, e.g. postgresql+asyncpg://user:pass@host/db",
    )

    # ------------------------------------------------------------------
    # Qdrant
    # ------------------------------------------------------------------
    qdrant_host: Optional[str] = Field(
        default=None,
        description="Qdrant server hostname or IP address.",
    )
    qdrant_port: int = Field(
        default=6333,
        description="Qdrant HTTP port.",
    )
    qdrant_api_key: Optional[str] = Field(
        default=None,
        description="Qdrant API key. Leave unset for unauthenticated access.",
    )
    qdrant_use_https: bool = Field(
        default=False,
        description="Connect to Qdrant over HTTPS.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Using lru_cache ensures the .env file is read only once per process.
    """
    return Settings()  # type: ignore[call-arg]