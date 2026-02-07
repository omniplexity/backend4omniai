"""v1 status endpoint."""

from datetime import datetime, UTC
from typing import Any

from fastapi import APIRouter, Request

from backend.config import get_settings

router = APIRouter()


@router.get("/status")
async def get_status(request: Request) -> dict[str, Any]:
    app = request.app
    start_time = getattr(app.state, "start_time", None)
    now = datetime.now(UTC)
    uptime_seconds = int((now - start_time).total_seconds()) if start_time else None

    registry = getattr(app.state, "provider_registry", None)
    providers = []
    if registry:
        for name in registry.list_providers():
            provider = registry.get_provider(name)
            healthy = False
            if provider:
                try:
                    healthy = await provider.healthcheck()
                except Exception:
                    healthy = False
            providers.append({"name": name, "healthy": healthy})

    settings = get_settings()
    return {
        "status": "ok",
        "version": request.app.version,
        "server_time": now.isoformat(),
        "uptime_seconds": uptime_seconds,
        "providers": providers,
        "sse": {
            "ping_interval_seconds": settings.sse_ping_interval_seconds,
        },
    }
