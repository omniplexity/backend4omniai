"""Provider registry for managing AI backends."""

from typing import Dict, List, Optional

from backend.config import Settings
from backend.core.logging import get_logger
from backend.providers.base import BaseProvider, ProviderType

logger = get_logger(__name__)


class ProviderRegistry:
    """Registry for managing AI providers."""

    def __init__(self, settings: Settings):
        """Initialize registry with settings."""
        self.settings = settings
        self.providers: Dict[str, BaseProvider] = {}
        self.default_provider = settings.provider_default

        # Initialize enabled providers
        self._init_providers()

    def _init_providers(self) -> None:
        """Initialize configured providers."""
        enabled = self.settings.providers_enabled_list

        for provider_name in enabled:
            try:
                provider = self._create_provider(provider_name)
                if provider:
                    self.providers[provider_name] = provider
                    logger.info(f"Initialized provider: {provider_name}")
            except Exception as e:
                logger.warning(f"Failed to initialize provider {provider_name}: {e}")

    def _create_provider(self, name: str) -> Optional[BaseProvider]:
        """Create a provider by name."""
        from backend.providers.lmstudio import LMStudioProvider
        from backend.providers.ollama import OllamaProvider
        from backend.providers.openai_compat import OpenAICompatProvider

        if name == ProviderType.LMSTUDIO.value:
            return LMStudioProvider(
                base_url=self.settings.lmstudio_base_url,
                timeout=self.settings.provider_timeout_seconds,
            )
        elif name == ProviderType.OLLAMA.value:
            return OllamaProvider(
                base_url=self.settings.ollama_base_url,
                timeout=self.settings.provider_timeout_seconds,
            )
        elif name == ProviderType.OPENAI_COMPAT.value:
            return OpenAICompatProvider(
                base_url=self.settings.openai_compat_base_url,
                api_key=self.settings.openai_compat_api_key,
                timeout=self.settings.provider_timeout_seconds,
            )
        else:
            logger.warning(f"Unknown provider type: {name}")
            return None

    def get_provider(self, name: str = None) -> Optional[BaseProvider]:
        """Get a provider by name, or the default."""
        name = name or self.default_provider
        return self.providers.get(name)

    def list_providers(self) -> List[str]:
        """List available provider names."""
        return list(self.providers.keys())

    async def healthcheck_all(self) -> Dict[str, bool]:
        """Check health of all providers."""
        results = {}
        for name, provider in self.providers.items():
            try:
                results[name] = await provider.healthcheck()
            except Exception:
                results[name] = False
        return results

    async def aclose(self) -> None:
        """Close all providers."""
        for name, provider in self.providers.items():
            try:
                await provider.aclose()
            except Exception as e:
                logger.warning(f"Error closing provider {name}: {e}")
