"""Provider registry read-only endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from app.config import get_settings
from app.providers import ProviderRegistry

router = APIRouter(tags=["providers"])


def get_registry(request: Request) -> ProviderRegistry:
    """Resolve provider registry from app state (initialize if missing)."""
    registry = getattr(request.app.state, "provider_registry", None)
    if registry is None:
        registry = ProviderRegistry(get_settings())
        request.app.state.provider_registry = registry
    return registry


@router.get("/providers")
async def list_providers(registry: ProviderRegistry = Depends(get_registry)) -> list[dict[str, Any]]:
    """List enabled providers with health indicator."""
    return await registry.list_providers()


@router.get("/providers/{provider_id}/models")
async def list_provider_models(
    provider_id: str, registry: ProviderRegistry = Depends(get_registry)
) -> list[str]:
    """List model identifiers for a specific provider."""
    models = await registry.list_models(provider_id)
    return [model.id for model in models]


@router.get("/providers/{provider_id}/health")
async def provider_health(
    provider_id: str, registry: ProviderRegistry = Depends(get_registry)
) -> dict[str, Any]:
    """Return provider health information."""
    return await registry.health(provider_id)


@router.get("/models")
async def list_all_models(registry: ProviderRegistry = Depends(get_registry)) -> list[dict[str, str]]:
    """
    Flattened model list with provider identifiers.

    Useful for UI dropdowns without an additional provider lookup.
    """
    models = await registry.list_models()
    return [{"id": model.id, "provider": model.provider.value} for model in models]
