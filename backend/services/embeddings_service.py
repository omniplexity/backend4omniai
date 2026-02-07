"""Embeddings service (provider selection + cosine similarity helpers)."""

from __future__ import annotations

import math
from typing import Optional

from backend.config import get_settings


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += float(x) * float(y)
        na += float(x) * float(x)
        nb += float(y) * float(y)
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


async def select_embeddings_provider(registry) -> Optional[object]:
    """Pick the first enabled provider that reports embeddings support."""
    if registry is None:
        return None

    settings = get_settings()
    preferred = settings.embeddings_provider_preference_list
    provider_items = getattr(registry, "providers", {}) or {}

    # Prefer configured order, then fallback to any provider.
    ordered = []
    for name in preferred:
        if name in provider_items:
            ordered.append((name, provider_items[name]))
    for name, p in provider_items.items():
        if name not in {n for n, _ in ordered}:
            ordered.append((name, p))

    for _name, provider in ordered:
        try:
            caps = await provider.capabilities()
            if getattr(caps, "embeddings", False):
                return provider
        except Exception:
            continue
    return None


async def embed_texts(registry, texts: list[str]) -> Optional[list[list[float]]]:
    """Generate embeddings for texts if enabled and provider available.

    Returns None when embeddings are disabled or unavailable.
    """
    settings = get_settings()
    if not settings.embeddings_enabled:
        return None

    provider = await select_embeddings_provider(registry)
    if provider is None:
        return None

    model = settings.embeddings_model or None
    try:
        return await provider.embed_texts(texts=texts, model=model)
    except Exception:
        return None

