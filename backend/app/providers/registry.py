"""Provider registry for enabled adapters."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.core import AppError, NotFoundError, get_logger
from app.providers.base import BaseProvider, ModelInfo, ProviderCapabilities
from app.providers.lmstudio import LMStudioProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai_compat import OpenAICompatProvider

logger = get_logger(__name__)


class ProviderRegistry:
    """Instantiate and manage enabled providers."""

    def __init__(
        self,
        settings: Settings,
        transport_overrides: dict[str, httpx.BaseTransport] | None = None,
    ):
        self.settings = settings
        self.providers: dict[str, BaseProvider] = {}
        self._transport_overrides = transport_overrides or {}
        self._initialize()

    def _transport(self, provider_id: str) -> httpx.BaseTransport | None:
        return self._transport_overrides.get(provider_id)

    def _initialize(self) -> None:
        for provider_id in self.settings.enabled_providers:
            provider: BaseProvider | None = None

            if provider_id == "lmstudio":
                provider = LMStudioProvider(
                    base_url=self.settings.lmstudio_base_url,
                    timeout=self.settings.provider_timeout_seconds,
                    max_retries=self.settings.provider_max_retries,
                    transport=self._transport(provider_id),
                )
            elif provider_id == "ollama":
                provider = OllamaProvider(
                    base_url=self.settings.ollama_base_url,
                    timeout=self.settings.provider_timeout_seconds,
                    max_retries=self.settings.provider_max_retries,
                    transport=self._transport(provider_id),
                )
            elif provider_id == "openai_compat":
                if not self.settings.openai_compat_base_url:
                    logger.warning(
                        "OPENAI_COMPAT_BASE_URL not set; skipping provider initialization"
                    )
                    continue
                provider = OpenAICompatProvider(
                    base_url=self.settings.openai_compat_base_url,
                    api_key=self.settings.openai_compat_api_key or None,
                    timeout=self.settings.provider_timeout_seconds,
                    max_retries=self.settings.provider_max_retries,
                    transport=self._transport(provider_id),
                )
            else:
                logger.warning("Unknown provider id in configuration", data={"id": provider_id})

            if provider:
                self.providers[provider.provider_type.value] = provider

        logger.info(
            "Provider registry initialized",
            data={"providers": list(self.providers.keys()), "default": self.settings.provider_default},
        )

    def get(self, provider_id: str) -> BaseProvider:
        """Resolve a provider by ID or raise NotFoundError."""
        provider = self.providers.get(provider_id)
        if not provider:
            raise NotFoundError(f"Provider '{provider_id}' not found")
        return provider

    async def list_providers(self) -> list[dict[str, Any]]:
        """Return enabled providers with optional health info."""
        providers: list[dict[str, Any]] = []
        for provider_id, provider in self.providers.items():
            ok = None
            try:
                ok = await provider.healthcheck()
            except AppError:
                ok = False
            providers.append(
                {
                    "id": provider_id,
                    "name": getattr(provider, "display_name", provider_id),
                    "enabled": True,
                    "ok": ok,
                }
            )
        return providers

    async def list_models(self, provider_id: str | None = None) -> list[ModelInfo]:
        """List models for a single provider or all providers."""
        if provider_id:
            provider = self.get(provider_id)
            return await provider.list_models()

        models: list[ModelInfo] = []
        for provider in self.providers.values():
            models.extend(await provider.list_models())
        return models

    async def health(self, provider_id: str) -> dict[str, Any]:
        """Return health check for a single provider."""
        provider = self.get(provider_id)
        try:
            ok = await provider.healthcheck()
            return {"ok": bool(ok)}
        except AppError as exc:
            return {"ok": False, "details": {"code": exc.code.value, "message": exc.message}}

    async def capabilities(
        self, provider_id: str, model: str | None = None
    ) -> ProviderCapabilities:
        """Return provider capabilities."""
        provider = self.get(provider_id)
        return await provider.capabilities(model=model)

    async def aclose(self) -> None:
        """Close all provider clients."""
        for provider in self.providers.values():
            try:
                await provider.aclose()
            except Exception:  # pragma: no cover - defensive
                logger.warning(
                    "Error closing provider client", data={"provider": provider.provider_type.value}
                )
