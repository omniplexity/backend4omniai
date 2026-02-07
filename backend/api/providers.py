"""Providers API endpoints."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.api.models import ModelInfo, ProviderInfo, ProviderStatus
from backend.auth.dependencies import get_current_user
from backend.core.logging import get_logger
from backend.db.models import User

logger = get_logger(__name__)
router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("/")
@router.get("", include_in_schema=False)
async def list_providers(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> List[ProviderStatus]:
    """List available providers and their status."""
    registry = getattr(request.app.state, "provider_registry", None)

    if not registry:
        return []

    results = []
    for name in registry.list_providers():
        provider = registry.get_provider(name)
        healthy = False
        if provider:
            try:
                healthy = await provider.healthcheck()
            except Exception:
                pass

        results.append(ProviderStatus(name=name, healthy=healthy))

    return results


@router.get("/health")
async def check_providers_health(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> Dict[str, bool]:
    """Check health of all providers."""
    registry = getattr(request.app.state, "provider_registry", None)

    if not registry:
        return {}

    return await registry.healthcheck_all()


@router.get("/{provider_name}")
async def get_provider_info(
    provider_name: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> ProviderInfo:
    """Get detailed info about a provider."""
    registry = getattr(request.app.state, "provider_registry", None)

    if not registry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No providers configured",
        )

    provider = registry.get_provider(provider_name)

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider not found: {provider_name}",
        )

    # Get health status
    healthy = False
    try:
        healthy = await provider.healthcheck()
    except Exception:
        pass

    # Get models - attempt even if not healthy to provide UX feedback
    models = []
    try:
        provider_models = await provider.list_models()
        models = [
            ModelInfo(
                id=m.id,
                name=m.name,
                provider=m.provider.value,
                context_length=m.context_length,
                supports_streaming=m.supports_streaming,
            )
            for m in provider_models
        ]
    except Exception as e:
        logger.warning(f"Failed to list models for {provider_name}: {e}")

    return ProviderInfo(
        name=provider_name,
        healthy=healthy,
        models=models,
    )


@router.get("/{provider_name}/models")
async def list_provider_models(
    provider_name: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> List[ModelInfo]:
    """List models available from a provider."""
    registry = getattr(request.app.state, "provider_registry", None)

    if not registry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No providers configured",
        )

    provider = registry.get_provider(provider_name)

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider not found: {provider_name}",
        )

    try:
        provider_models = await provider.list_models()
        return [
            ModelInfo(
                id=m.id,
                name=m.name,
                provider=m.provider.value,
                context_length=m.context_length,
                supports_streaming=m.supports_streaming,
            )
            for m in provider_models
        ]
    except Exception as e:
        logger.error(f"Failed to list models for {provider_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to list models: {e}",
        )


@router.get("/{provider_name}/capabilities")
async def get_provider_capabilities(
    provider_name: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get capabilities of a provider."""
    registry = getattr(request.app.state, "provider_registry", None)

    if not registry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No providers configured",
        )

    provider = registry.get_provider(provider_name)

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider not found: {provider_name}",
        )

    try:
        caps = await provider.capabilities()
        return {
            "streaming": caps.streaming,
            "function_calling": caps.function_calling,
            "vision": caps.vision,
            "embeddings": caps.embeddings,
            "voice": caps.voice,
            "stt": caps.stt,
            "tts": caps.tts,
        }
    except Exception as e:
        logger.error(f"Failed to get capabilities for {provider_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to get capabilities: {e}",
        )
