"""
Health check endpoints.

Provides liveness and readiness probes for monitoring.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


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
async def readiness() -> dict[str, Any]:
    """
    Readiness check endpoint.

    Returns service readiness status. Checks that all required
    dependencies are available. Used by orchestrators to determine
    if the service should receive traffic.
    """
    # TODO: Add actual dependency checks (db, providers) in Phase 2
    checks: dict[str, bool] = {
        "database": True,  # Placeholder - will check actual connection
        "config": True,
    }

    all_ready = all(checks.values())

    return {
        "status": "ready" if all_ready else "not_ready",
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": checks,
    }
