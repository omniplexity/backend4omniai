"""v1 models endpoint."""

from typing import Any, List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from backend.auth.dependencies import get_current_user
from backend.db.models import User

router = APIRouter()


class ModelCapabilities(BaseModel):
    provider: str
    model: str
    context_length: int | None = None
    supports_vision: bool = False
    supports_tools: bool = False
    supports_json: bool = False
    supports_streaming: bool = True


@router.get("/models", response_model=List[ModelCapabilities])
async def list_models(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    registry = getattr(request.app.state, "provider_registry", None)
    if not registry:
        return []

    results: list[ModelCapabilities] = []
    for provider_name in registry.list_providers():
        provider = registry.get_provider(provider_name)
        if not provider:
            continue
        try:
            healthy = await provider.healthcheck()
        except Exception:
            healthy = False
        if not healthy:
            continue
        try:
            caps = await provider.capabilities()
        except Exception:
            caps = None
        try:
            models = await provider.list_models()
        except Exception:
            models = []
        for model in models:
            supports_tools = bool(getattr(model, "supports_functions", False)) or bool(getattr(caps, "function_calling", False))
            results.append(
                ModelCapabilities(
                    provider=provider_name,
                    model=model.id,
                    context_length=model.context_length,
                    supports_vision=bool(getattr(caps, "vision", False)),
                    supports_tools=supports_tools,
                    supports_json=supports_tools,
                    supports_streaming=bool(getattr(model, "supports_streaming", True)),
                )
            )
    return results
