"""Application settings using Pydantic BaseSettings."""

import os
import secrets
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_default_db_path() -> str:
    """Get absolute path to default SQLite database."""
    # Get the directory containing this settings file (backend/config/)
    config_dir = os.path.dirname(os.path.abspath(__file__))
    # Go up one level to backend/
    backend_dir = os.path.dirname(config_dir)
    # Path to database file
    db_path = os.path.join(backend_dir, "data", "omniai.db")
    # Convert to absolute path with sqlite:/// prefix
    return f"sqlite:///{db_path}"


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server
    # Explicit environment selector. Keep this separate from DEBUG so production
    # checks don't accidentally trigger just because SECRET_KEY looks "strong".
    environment: str = Field(default="development")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    log_file: Optional[str] = Field(default=None)

    # Security
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(64))
    cors_origins: str = Field(default="http://localhost:3000,https://omniplexity.github.io")
    rate_limit_rpm: int = Field(default=60)
    rate_limit_user_rpm: int = Field(default=60)
    max_request_bytes: int = Field(default=1048576)
    voice_max_request_bytes: int = Field(default=26214400)

    # Authentication
    session_cookie_name: str = Field(default="omni_session")
    session_ttl_seconds: int = Field(default=604800)
    cookie_secure: bool = Field(default=True)
    cookie_samesite: str = Field(default="lax")
    cookie_domain: str = Field(default="")
    csrf_header_name: str = Field(default="X-CSRF-Token")
    csrf_cookie_name: str = Field(default="omni_csrf")
    invite_required: bool = Field(default=True)

    # Bootstrap admin (startup-only, env-driven)
    bootstrap_admin_enabled: bool = Field(default=False)
    bootstrap_admin_username: str = Field(default="")
    bootstrap_admin_email: str = Field(default="")
    bootstrap_admin_password: str = Field(default="")

    # Database
    database_url: str = Field(default_factory=_get_default_db_path)
    database_url_postgres: str = Field(default="")

    @property
    def effective_database_url(self) -> str:
        """Get the effective database URL (Postgres takes precedence if set)."""
        return self.database_url_postgres or self.database_url

    # Media storage
    media_storage_path: str = Field(default="./data/uploads")

    # Providers
    provider_default: str = Field(default="lmstudio")
    providers_enabled: str = Field(default="lmstudio")
    provider_timeout_seconds: int = Field(default=30)
    provider_max_retries: int = Field(default=1)
    sse_ping_interval_seconds: int = Field(default=10)
    readiness_check_providers: bool = Field(default=False)

    # Embeddings (semantic search / RAG)
    embeddings_enabled: bool = Field(default=False)
    embeddings_model: str = Field(default="")
    embeddings_provider_preference: str = Field(default="openai_compat,ollama,lmstudio")

    # LM Studio
    lmstudio_base_url: str = Field(default="http://host.docker.internal:1234")

    # Ollama
    ollama_base_url: str = Field(default="http://127.0.0.1:11434")

    # OpenAI-compatible
    openai_compat_base_url: str = Field(default="")
    openai_compat_api_key: str = Field(default="")

    # Voice
    voice_provider_preference: str = Field(default="whisper,openai_compat")
    voice_whisper_model: str = Field(default="base")
    voice_whisper_device: str = Field(default="cpu")
    voice_openai_audio_model: str = Field(default="whisper-1")

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        if not self.cors_origins:
            return []
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def providers_enabled_list(self) -> List[str]:
        """Parse enabled providers from comma-separated string."""
        if not self.providers_enabled:
            return []
        return [p.strip() for p in self.providers_enabled.split(",") if p.strip()]

    @property
    def embeddings_provider_preference_list(self) -> List[str]:
        if not self.embeddings_provider_preference:
            return []
        return [
            p.strip()
            for p in self.embeddings_provider_preference.split(",")
            if p.strip()
        ]

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment.lower() == "production"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        upper = v.upper()
        if upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return upper

    @field_validator("cookie_samesite")
    @classmethod
    def validate_cookie_samesite(cls, v: str) -> str:
        """Normalize + validate SameSite cookie attribute."""
        vv = (v or "").strip().lower()
        if vv not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be one of: lax, strict, none")
        return vv

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        vv = (v or "").strip().lower()
        if vv not in {"development", "staging", "production"}:
            raise ValueError("ENVIRONMENT must be one of: development, staging, production")
        return vv

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, v: str, info):  # type: ignore[override]
        env = (info.data.get("environment") or "development").strip().lower()
        origins = [o.strip() for o in (v or "").split(",") if o.strip()]
        if env == "production":
            # Fail closed: require https origins only.
            bad = [o for o in origins if o.startswith("http://")]
            if bad:
                raise ValueError(f"In production, CORS_ORIGINS must be https-only; got: {bad}")
        return v

    @model_validator(mode="after")
    def validate_cross_field_constraints(self) -> "Settings":
        # SameSite=None requires Secure=true.
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true when COOKIE_SAMESITE=none")
        return self


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
