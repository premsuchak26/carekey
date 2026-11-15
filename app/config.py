"""Application configuration module using pydantic-settings.

Reads settings from environment variables and optional .env file.
"""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """CareKey runtime application settings."""

    app_name: str = Field(default="CareKey", description="Application name.")
    environment: Literal["development", "production", "test"] = Field(
        default="development", description="Current operating environment."
    )
    debug: bool = Field(default=False, description="Enable debug mode and verbose logging.")
    host: str = Field(default="0.0.0.0", description="Host interface to bind to.")
    port: int = Field(default=8000, ge=1, le=65535, description="Port number to listen on.")
    secret_key: str = Field(
        default="change-this-in-production-to-a-secure-random-key",
        description="Application secret key used for session/token cryptographic operations.",
    )

    repository_backend: Literal["memory", "firestore"] = Field(
        default="memory",
        validation_alias=AliasChoices(
            "REPOSITORY_BACKEND",
            "repository_backend",
            "REPOSITORY_TYPE",
            "repository_type",
        ),
        description=(
            "Persistence backend implementation ('memory' for local dev/testing, "
            "'firestore' for production)."
        ),
    )
    firestore_project_id: str | None = Field(
        default=None,
        description="Google Cloud Project ID for Firestore if using firestore backend.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def repository_type(self) -> Literal["memory", "firestore"]:
        """Backwards-compatibility alias for repository_backend."""
        return self.repository_backend


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of application settings.

    Returns:
        Settings: Instantiated and validated application configuration.
    """
    return Settings()
