"""Deterministic provider/model selection."""
from __future__ import annotations

import inspect
from typing import Iterable

from backend.app.config.settings import settings
from backend.app.db.models import Conversation, Project, User
from backend.app.domain.providers.registry import registry


class ModelSelectionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_PROVIDER_ALIASES = {
    "lm_studio": "lmstudio",
    "lmstudio": "lmstudio",
    "openai_compat": "openai",
    "openai": "openai",
    "ollama": "ollama",
}


def normalize_provider_id(provider_id: str | None) -> str | None:
    if not provider_id:
        return None
    key = provider_id.strip().lower()
    return _PROVIDER_ALIASES.get(key, key)


def _model_ids(models: Iterable) -> list[str]:
    ids: list[str] = []
    for model in models:
        model_id = getattr(model, "id", None)
        if model_id is None:
            model_id = str(model)
        ids.append(model_id)
    return ids


def _pick_model(models: list[str]) -> str | None:
    if not models:
        return None
    priorities = [p.lower() for p in settings.model_priority or []]
    if priorities:
        for term in priorities:
            for model_id in models:
                if term and term in model_id.lower():
                    return model_id
    return models[0]


async def select_provider_model(
    user: User,
    project: Project | None,
    conversation: Conversation | None,
    requested_provider: str | None = None,
    requested_model: str | None = None,
) -> tuple[str, str]:
    """Select provider/model with deterministic fallback rules."""
    cache: dict[str, list[str]] = {}

    async def get_models(provider_id: str) -> list[str]:
        normalized = normalize_provider_id(provider_id)
        if not normalized:
            return []
        if normalized in cache:
            return cache[normalized]
        provider = registry.get(normalized)
        if not provider:
            cache[normalized] = []
            return []

        models = provider.list_models()
        if inspect.isawaitable(models):
            models = await models
        model_ids = _model_ids(models)
        cache[normalized] = model_ids
        return model_ids

    async def validate_pair(provider_id: str, model_id: str) -> tuple[str, str] | None:
        normalized = normalize_provider_id(provider_id)
        if not normalized:
            return None
        models = await get_models(normalized)
        if model_id in models:
            return normalized, model_id
        return None

    # (1) explicit request
    if requested_provider and requested_model:
        validated = await validate_pair(requested_provider, requested_model)
        if validated:
            return validated
        raise ModelSelectionError("invalid_model", "Requested model is not available")

    if requested_provider and not requested_model:
        models = await get_models(requested_provider)
        picked = _pick_model(models)
        if picked:
            return normalize_provider_id(requested_provider) or requested_provider.strip().lower(), picked

    # (2) conversation pinned
    if conversation and conversation.provider and conversation.model:
        validated = await validate_pair(conversation.provider, conversation.model)
        if validated:
            return validated

    # (3) project defaults
    if project and project.default_provider and project.default_model:
        validated = await validate_pair(project.default_provider, project.default_model)
        if validated:
            return validated

    # (4) user defaults
    if user.default_provider and user.default_model:
        validated = await validate_pair(user.default_provider, user.default_model)
        if validated:
            return validated

    # (5) env defaults
    if settings.default_provider and settings.default_model:
        validated = await validate_pair(settings.default_provider, settings.default_model)
        if validated:
            return validated

    # (6) provider priority scan
    provider_order = [normalize_provider_id(p) for p in (settings.provider_priority or []) if p]
    provider_order = [p for p in provider_order if p]
    available_ids = [p.get("provider_id") for p in registry.list_providers()]
    for provider_id in available_ids:
        if provider_id and provider_id not in provider_order:
            provider_order.append(provider_id)

    for provider_id in provider_order:
        models = await get_models(provider_id)
        picked = _pick_model(models)
        if picked:
            return provider_id, picked

    raise ModelSelectionError("no_models_available", "No models are available")
