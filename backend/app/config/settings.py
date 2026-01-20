from __future__ import annotations

from pathlib import Path

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Prefer repo-root .env, then backend/.env, then env vars.
    model_config = ConfigDict(env_file=("../.env", ".env"), extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8787
    log_level: str = "INFO"
    environment: str = "dev"  # New setting for test hooks

    # Comma-separated support can be layered later; for now keep list[str]
    cors_origins: list[str] = ["https://omniplexity.github.io"]

    # Database - compute repo-root path deterministically
    database_url: str = ""

    # Auth
    secret_key: str = "dev-secret-key-change-in-prod"  # Required in prod; allow dev defaults but warn
    csrf_secret: str = "dev-csrf-secret-change-in-prod"  # Required in prod
    session_cookie_name: str = "omniplexity_session"
    session_ttl_seconds: int = 86400 * 7  # 7 days
    cookie_secure: bool = False  # Dev-safe default; set True in production .env
    cookie_samesite: str = "lax"  # Dev-safe default; set "None" in production .env

    def __init__(self, **data):
        super().__init__(**data)
        if not self.database_url:  # Only set default if not overridden by env
            repo_root = Path(__file__).resolve().parents[3]
            db_path = repo_root / "data" / "omniplexity.db"
            self.database_url = f"sqlite:///{db_path.as_posix()}"

        # Set production cookie defaults if not in dev environment
        if self.environment != "dev":
            # Only override if not explicitly set via env
            if 'cookie_secure' not in data:
                self.cookie_secure = True
            if 'cookie_samesite' not in data:
                self.cookie_samesite = "None"
    invite_only: bool = True
    admin_bootstrap_token: str = "dev-bootstrap-token-change-in-prod"  # One-time use

    # Providers
    lmstudio_base_url: str = "http://127.0.0.1:1234/v1"
    lmstudio_timeout_seconds: int = 120
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_timeout_seconds: int = 120
    openai_compat_base_url: str = ""
    openai_api_key: str = ""
    openai_timeout_seconds: int = 120

    # SSE
    sse_heartbeat_seconds: int = 15
    sse_client_disconnect_grace_seconds: int = 2

    # Origin lock for tunnel protection
    origin_lock_enabled: bool = False
    origin_lock_secret: str = ""  # Shared secret set in tunnel config


settings = Settings()