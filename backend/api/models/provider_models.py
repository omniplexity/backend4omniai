"""Shared provider models for API endpoints.

This module contains Pydantic models used by both legacy (/api/providers)
and canonical (/v1/providers) API endpoints to avoid code duplication.
"""

from typing import Any, Dict, List

from pydantic import BaseModel


class ModelInfo(BaseModel):
    """Information about a language model."""

    id: str
    name: str
    provider: str | None = None
    context_length: int | None = None
    supports_streaming: bool = True


class ProviderStatus(BaseModel):
    """Health status of a provider."""

    name: str
    healthy: bool


class ProviderInfo(BaseModel):
    """Detailed information about a provider."""

    name: str
    healthy: bool
    models: List["ModelInfo"]
    capabilities: Dict[str, Any] | None = None


class ProviderCapabilities(BaseModel):
    """Capabilities supported by a provider."""

    streaming: bool
    function_calling: bool
    vision: bool
    embeddings: bool
    voice: bool
    stt: bool
    tts: bool


# Rebuild model to resolve forward references
ProviderInfo.model_rebuild()
