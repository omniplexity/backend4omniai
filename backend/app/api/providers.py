from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.auth.deps import require_active_user
from backend.app.providers.registry import registry

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/")
async def list_providers(
    include_models: bool = Query(False, description="Include models list for each provider"),
    user=Depends(require_active_user),
):
    if include_models:
        return await registry.list_providers_with_models()
    else:
        return registry.list_providers()


@router.get("/{provider_id}/models")
async def list_provider_models(
    provider_id: str,
    user=Depends(require_active_user),
):
    try:
        models = await registry.list_models(provider_id)
        return {"models": [{"id": m.id, "label": m.label} for m in models]}
    except HTTPException:
        raise
    except Exception:
        # Return empty list if provider unreachable
        return {"models": []}


@router.get("/{provider_id}/health")
async def provider_health(
    provider_id: str,
    user=Depends(require_active_user),
):
    health = await registry.health(provider_id)
    return health.__dict__
