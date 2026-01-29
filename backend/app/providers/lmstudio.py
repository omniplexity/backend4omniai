"""LM Studio provider (OpenAI-compatible) adapter."""

from __future__ import annotations

import httpx

from app.providers.base import ProviderType
from app.providers.openai_compat import OpenAICompatProvider


class LMStudioProvider(OpenAICompatProvider):
    """LM Studio uses the OpenAI-compatible API surface."""

    def __init__(
        self,
        base_url: str,
        timeout: int,
        max_retries: int,
        transport: httpx.BaseTransport | None = None,
    ):
        super().__init__(
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            api_key=None,
            provider_type=ProviderType.LMSTUDIO,
            display_name="LM Studio",
            transport=transport,
        )
