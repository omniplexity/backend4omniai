"""
OmniAI Backend Application.

FastAPI application with structured logging, error handling,
and security middleware.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin_router, auth_router, health_router
from app.config import get_settings
from app.core import (
    ChatCSRFMiddleware,
    RequestContextMiddleware,
    RequestSizeLimitMiddleware,
    get_logger,
    setup_exception_handlers,
    setup_logging,
)
from app.db import dispose_engine, verify_database_connection
from app.providers import ProviderRegistry

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    settings = get_settings()

    # Startup
    setup_logging(level=settings.log_level, json_output=not settings.debug)
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
    else:
        logger.warning(
            "Database connection failed - run 'alembic upgrade head' to initialize"
        )

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
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.max_request_bytes)

    # 2. Request context (inject request ID, log requests)
    app.add_middleware(RequestContextMiddleware)

    # 3. Chat CSRF middleware (runs after auth cookies are parsed)
    app.add_middleware(ChatCSRFMiddleware)

    # 3. CORS (must be configured correctly for GitHub Pages frontend)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*", settings.csrf_header_name],
        expose_headers=["X-Request-ID"],
    )

    # Register routers
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    from app.api.chat import router as chat_router
    from app.api.providers import router as providers_router

    app.include_router(providers_router)
    app.include_router(chat_router)

    # TODO: Add chat router (Phase 4)
    # TODO: Add conversations router (Phase 4)
    # TODO: Add models router (Phase 4)

    return app


# Create application instance
app = create_app()
