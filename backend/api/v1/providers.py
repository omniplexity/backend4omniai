"""v1 providers endpoint.

Exposes Provider Agent interfaces for listing providers and models.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from backend.agents.provider import ProviderAgent
from backend.api.models import (
    ModelInfo,
    ProviderCapabilities,
    ProviderInfo,
    ProviderStatus,
)
from backend.auth.dependencies import get_current_user
from backend.config import get_settings
from backend.db import get_db
from backend.db.models import User

router = APIRouter(prefix="/providers", tags=["v1-providers"])


def _create_provider_agent(request: Request) -> ProviderAgent:
    """Create a Provider Agent instance."""
    registry = getattr(request.app.state, "provider_registry", None)
    settings = get_settings()
    return ProviderAgent(settings, registry)


@router.get("", response_model=List[ProviderStatus])
async def list_providers(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> List[ProviderStatus]:
    """List all available providers and their health status."""
    agent = _create_provider_agent(request)
    
    provider_names = await agent.list_providers()
    results = []
    
    for name in provider_names:
        health = await agent.get_provider_health(name)
        results.append(ProviderStatus(
            name=name,
            healthy=health.get("healthy", False),
        ))
    
    return results


@router.get("/{provider_name}", response_model=ProviderInfo)
async def get_provider_info(
    provider_name: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> ProviderInfo:
    """Get detailed info about a provider including models and capabilities."""
    agent = _create_provider_agent(request)
    
    provider_names = await agent.list_providers()
    if provider_name not in provider_names:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider not found: {provider_name}",
        )
    
    health = await agent.get_provider_health(provider_name)
    models = await agent.list_models(provider_name)
    capabilities = await agent.get_capabilities(provider_name)
    
    return ProviderInfo(
        name=provider_name,
        healthy=health.get("healthy", False),
        models=[
            ModelInfo(
                id=m.id,
                name=m.name,
                context_length=m.context_length,
                supports_streaming=m.supports_streaming,
            )
            for m in models
        ],
        capabilities={
            "streaming": capabilities.streaming,
            "function_calling": capabilities.function_calling,
            "vision": capabilities.vision,
            "embeddings": capabilities.embeddings,
            "voice": capabilities.voice,
            "stt": capabilities.stt,
            "tts": capabilities.tts,
        },
    )


@router.get("/{provider_name}/models", response_model=List[ModelInfo])
async def list_provider_models(
    provider_name: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> List[ModelInfo]:
    """List models available from a specific provider."""
    agent = _create_provider_agent(request)
    
    provider_names = await agent.list_providers()
    if provider_name not in provider_names:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider not found: {provider_name}",
        )
    
    models = await agent.list_models(provider_name)
    
    return [
        ModelInfo(
            id=m.id,
            name=m.name,
            context_length=m.context_length,
            supports_streaming=m.supports_streaming,
        )
        for m in models
    ]


@router.get("/{provider_name}/capabilities", response_model=ProviderCapabilities)
async def get_provider_capabilities(
    provider_name: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> ProviderCapabilities:
    """Get capabilities of a specific provider."""
    agent = _create_provider_agent(request)
    
    provider_names = await agent.list_providers()
    if provider_name not in provider_names:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider not found: {provider_name}",
        )
    
    capabilities = await agent.get_capabilities(provider_name)
    
    return ProviderCapabilities(
        streaming=capabilities.streaming,
        function_calling=capabilities.function_calling,
        vision=capabilities.vision,
        embeddings=capabilities.embeddings,
        voice=capabilities.voice,
        stt=capabilities.stt,
        tts=capabilities.tts,
    )


# Update forward references
ProviderInfo.model_rebuild()
