"""
Application settings using Pydantic Settings.

Loads configuration from environment variables and .env file.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation and defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server
    host: str = Field(default="127.0.0.1", description="Server bind address")
    port: int = Field(default=8000, ge=1, le=65535, description="Server port")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # Security
    secret_key: str = Field(
        default="INSECURE_DEFAULT_CHANGE_ME",
        min_length=16,
        description="Secret key for signing",
    )
    cors_origins: str = Field(
        default="https://omniplexity.github.io",
        description="Comma-separated CORS origins",
    )
    rate_limit_rpm: int = Field(default=60, ge=1, description="Rate limit per minute")

    # Authentication - Session cookies
    session_cookie_name: str = Field(
        default="omni_session", description="Session cookie name"
    )
    session_ttl_seconds: int = Field(
        default=604800, ge=60, description="Session TTL in seconds (default 7 days)"
    )
    cookie_secure: bool = Field(
        default=True, description="Require HTTPS for cookies"
    )
    cookie_samesite: str = Field(
        default="lax", description="SameSite cookie policy (lax|strict|none)"
    )
    cookie_domain: str = Field(
        default="", description="Cookie domain (empty for current domain)"
    )

    # Authentication - CSRF
    csrf_header_name: str = Field(
        default="X-CSRF-Token", description="CSRF header name"
    )
    csrf_cookie_name: str = Field(
        default="omni_csrf", description="CSRF cookie name"
    )

    # Authentication - Registration
    invite_required: bool = Field(
        default=True, description="Require invite code for registration"
    )

    # Request limits
    max_request_bytes: int = Field(
        default=1048576, ge=1024, description="Max request body bytes (default 1MB)"
    )
    sse_ping_interval_seconds: int = Field(
        default=10,
        ge=0,
        description="Keep-alive ping interval for SSE streams in seconds (0 disables)",
    )

    # Database
    database_url: str = Field(
        default="sqlite:///./data/omniai.db", description="Database connection URL"
    )

    # Providers - General
    provider_default: str = Field(
        default="lmstudio",
        description="Default provider (lmstudio, ollama, openai_compat)",
    )
    providers_enabled: str = Field(
        default="lmstudio",
        description="Comma-separated providers to enable (lmstudio,ollama,openai_compat)",
    )
    provider_timeout_seconds: int = Field(
        default=30, ge=5, le=300, description="Provider request timeout"
    )
    provider_max_retries: int = Field(
        default=1, ge=0, le=5, description="Max retries for provider requests"
    )

    # Providers - LM Studio (OpenAI compatible)
    lmstudio_base_url: str = Field(
        default="http://127.0.0.1:1234", description="LM Studio API base URL"
    )

    # Providers - Ollama
    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434", description="Ollama API base URL"
    )

    # Providers - OpenAI Compatible
    openai_compat_base_url: str = Field(
        default="", description="OpenAI-compatible API base URL"
    )
    openai_compat_api_key: str = Field(
        default="", description="OpenAI-compatible API key"
    )

    @property
    def enabled_providers(self) -> list[str]:
        """Parse enabled providers from comma-separated string."""
        allowed = {"lmstudio", "ollama", "openai_compat"}
        parsed = []
        for provider in self.providers_enabled.split(","):
            provider_id = provider.strip().lower()
            if not provider_id or provider_id not in allowed:
                continue
            if provider_id == "openai_compat" and not self.openai_compat_base_url:
                # Skip incomplete configuration
                continue
            parsed.append(provider_id)

        # Ensure default is present if valid and configured
        if (
            self.provider_default == "openai_compat"
            and not self.openai_compat_base_url
        ):
            raise ValueError(
                "OPENAI_COMPAT_BASE_URL must be set when provider_default=openai_compat"
            )

        if self.provider_default in allowed and self.provider_default not in parsed:
            parsed.append(self.provider_default)

        return parsed

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return upper

    @field_validator("cookie_samesite")
    @classmethod
    def validate_cookie_samesite(cls, v: str) -> str:
        """Ensure SameSite value is valid."""
        valid = {"lax", "strict", "none"}
        lower = v.lower()
        if lower not in valid:
            raise ValueError(f"cookie_samesite must be one of {valid}")
        return lower

    @field_validator("provider_default")
    @classmethod
    def validate_provider_default(cls, v: str) -> str:
        """Ensure provider_default is one of the supported providers."""
        allowed = {"lmstudio", "ollama", "openai_compat"}
        lower = v.lower()
        if lower not in allowed:
            raise ValueError(f"provider_default must be one of {allowed}")
        return lower

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins into a list."""
        if not self.cors_origins:
            return []
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.debug and self.secret_key != "INSECURE_DEFAULT_CHANGE_ME"

    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite database."""
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
