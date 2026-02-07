"""
OmniAI Backend Application.

FastAPI application with structured logging, error handling,
and security middleware.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import (
    admin_router,
    auth_router,
    diag_router,
    health_router,
    voice_router,
    tools_router,
    media_router,
    memory_router,
    knowledge_router,
    plan_router,
    projects_router,
    context_blocks_router,
    artifacts_router,
    workflows_router,
)
from backend.auth.bootstrap import ensure_bootstrap_admin
from backend.config import get_settings
from backend.core import (
    ChatCSRFMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    RequestSizeLimitMiddleware,
    get_logger,
    setup_exception_handlers,
    setup_logging,
)
from backend.db import dispose_engine, verify_database_connection
from backend.providers import ProviderRegistry

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    settings = get_settings()

    # Startup
    setup_logging(
        level=settings.log_level,
        json_output=not settings.debug,
        log_file=settings.log_file or None,
    )
    logger.info(
        "Starting OmniAI backend",
        data={
            "host": settings.host,
            "port": settings.port,
            "debug": settings.debug,
            "cors_origins": settings.cors_origins_list,
        },
    )

    # Verify database connectivity (does NOT run migrations)
    db_ok = verify_database_connection()
    if db_ok:
        logger.info("Database connection verified")
        try:
            ensure_bootstrap_admin(settings)
        except Exception as exc:
            logger.error("Bootstrap admin failed", data={"error": str(exc)})
    else:
        logger.warning(
            "Database connection failed - run 'alembic upgrade head' to initialize"
        )

    # Record start time for uptime tracking
    _app.state.start_time = datetime.now(UTC)

    # Initialize provider registry unless provided (useful in tests)
    registry_created = False
    if not hasattr(_app.state, "provider_registry"):
        _app.state.provider_registry = ProviderRegistry(settings)
        registry_created = True

    if not settings.is_production:
        logger.warning("Running with default secret key - NOT FOR PRODUCTION")

    yield

    # Shutdown
    logger.info("Shutting down OmniAI backend")
    dispose_engine()
    if registry_created:
        await _app.state.provider_registry.aclose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="OmniAI",
        description="Privacy-first AI chat backend for LM Studio, Ollama, and OpenAI-compatible endpoints",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Setup exception handlers (must be before middleware)
    setup_exception_handlers(app)

    # Add middleware (order matters - last added = first executed)
    # 1. Request size limit (reject oversized requests early)
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=settings.max_request_bytes,
        voice_max_bytes=settings.voice_max_request_bytes,
    )

    # 2. Rate limiting (per-IP + per-user, in-memory)
    app.add_middleware(
        RateLimitMiddleware,
        ip_requests_per_minute=settings.rate_limit_rpm,
        user_requests_per_minute=settings.rate_limit_user_rpm,
    )

    # 3. Request context (inject request ID, log requests)
    app.add_middleware(RequestContextMiddleware)

    # 4. Chat CSRF middleware (runs after auth cookies are parsed)
    app.add_middleware(ChatCSRFMiddleware)

    # 5. CORS (must be configured correctly for GitHub Pages frontend)
    allow_origin_regex = None
    if not settings.is_production:
        # Allow localhost, 127.0.0.1, and ngrok domains in development
        allow_origin_regex = r"^https?://(localhost|127\\.0\\.0\\.1)(:\\d+)?$|^https://[a-zA-Z0-9-]+\\.ngrok-free\\.dev$"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*", settings.csrf_header_name],
        expose_headers=["X-Request-ID"],
        allow_origin_regex=allow_origin_regex,
    )

    # Register routers
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(diag_router)
    app.include_router(admin_router)
    app.include_router(voice_router)
    app.include_router(tools_router)
    app.include_router(media_router)
    app.include_router(memory_router)
    app.include_router(knowledge_router)
    app.include_router(plan_router)
    app.include_router(projects_router)
    app.include_router(context_blocks_router)
    app.include_router(artifacts_router)
    app.include_router(workflows_router)
    from backend.api.chat import router as chat_router
    from backend.api.providers import router as providers_router
    from backend.api.v1 import router as v1_router

    app.include_router(providers_router)
    app.include_router(chat_router)
    app.include_router(v1_router)

    return app


# Create application instance
app = create_app()
