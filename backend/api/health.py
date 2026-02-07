"""
Health check endpoints.

Provides liveness and readiness probes for monitoring.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.db import verify_database_connection
from backend.services.capabilities_service import compute_service_capabilities

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/healthz")
async def healthcheck() -> dict[str, Any]:
    """
    Health check endpoint.

    Returns basic service health status. Used by load balancers,
    orchestrators, and monitoring systems.
    """
    settings = get_settings()

    return {
        "status": "ok",
        "version": "0.1.0",
        "timestamp": datetime.now(UTC).isoformat(),
        "debug": settings.debug,
    }


@router.get("/readyz")
async def readiness(request: Request) -> JSONResponse:
    """
    Readiness check endpoint.

    Returns service readiness status. Checks that all required
    dependencies are available. Used by orchestrators to determine
    if the service should receive traffic.
    """
    checks: dict[str, bool] = {
        "database": verify_database_connection(),
        "config": True,
    }
    details: dict[str, Any] = {}

    settings = get_settings()
    if settings.readiness_check_providers:
        providers_ok = True
        provider_checks: dict[str, bool] = {}
        registry = getattr(request.app.state, "provider_registry", None)
        if registry is not None:
            for provider_id, provider in registry.providers.items():
                try:
                    ok = await provider.healthcheck()
                except Exception:  # pragma: no cover - defensive
                    ok = False
                provider_checks[provider_id] = bool(ok)
                if not ok:
                    providers_ok = False
        else:
            providers_ok = False
        checks["providers"] = providers_ok
        details["providers"] = provider_checks

    all_ready = all(checks.values())
    payload: dict[str, Any] = {
        "status": "ready" if all_ready else "not_ready",
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": checks,
    }
    if details:
        payload["details"] = details

    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )


@router.get("/capabilities")
async def get_capabilities(request: Request) -> dict[str, Any]:
    """
    Get service capabilities.
    
    Returns feature flags and capabilities that the frontend can use
    to enable/disable features dynamically.
    """
    registry = getattr(request.app.state, "provider_registry", None)
    return await compute_service_capabilities(registry)
