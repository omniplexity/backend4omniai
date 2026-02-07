"""v1 ops endpoints."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.auth.dependencies import get_admin_user, get_current_user
from backend.config import get_settings
from backend.db.models import User

router = APIRouter(tags=["v1-ops"])


@router.get("/providers/health")
async def providers_health(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> Dict[str, bool]:
    registry = getattr(request.app.state, "provider_registry", None)
    if not registry:
        return {}
    return await registry.healthcheck_all()


@router.get("/ops/limits")
async def ops_limits(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    settings = get_settings()
    return {
        "rate_limit_rpm": settings.rate_limit_rpm,
        "max_request_bytes": settings.max_request_bytes,
        "voice_max_request_bytes": settings.voice_max_request_bytes,
    }


@router.get("/audit/recent")
async def recent_audit(
    request: Request,
    admin: User = Depends(get_admin_user),
) -> Dict[str, Any]:
    # Placeholder until audit log is implemented
    return {"entries": []}
