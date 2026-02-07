"""Provider Agent.

Manages AI model providers (LM Studio, Ollama, OpenAI-compatible endpoints).
Provides interfaces for listing models, health checks, and chat operations.
"""

from typing import List, Dict, Optional, Any, AsyncGenerator
from dataclasses import dataclass

from backend.providers import ProviderRegistry
from backend.config import Settings


@dataclass
class ModelInfo:
    """Model information."""
    id: str
    name: str
    provider: str
    context_length: Optional[int] = None
    supports_streaming: bool = True
    capabilities: Dict[str, Any] = None


@dataclass  
class ProviderCapabilities:
    """Provider capabilities."""
    streaming: bool = True
    function_calling: bool = False
    vision: bool = False
    embeddings: bool = False
    voice: bool = False
    stt: bool = False
    tts: bool = False


@dataclass
class ChatMessage:
    """Chat message for completion requests."""
    role: str
    content: str


@dataclass
class ChatRequest:
    """Chat completion request."""
    messages: List[ChatMessage]
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    stream: bool = True


@dataclass
class ChatResponse:
    """Chat completion response."""
    content: str
    provider: str
    model: str
    tokens_prompt: Optional[int] = None
    tokens_completion: Optional[int] = None
    finish_reason: Optional[str] = None


class ProviderAgent:
    """Agent for managing AI providers."""

    def __init__(self, settings: Settings, registry: ProviderRegistry = None):
        """Initialize the Provider Agent.
        
        Args:
            settings: Application settings
            registry: Optional ProviderRegistry instance (created if not provided)
        """
        self.settings = settings
        self._registry = registry

    @property
    def registry(self) -> ProviderRegistry:
        """Get or create the provider registry."""
        if self._registry is None:
            self._registry = ProviderRegistry(self.settings)
        return self._registry

    async def list_providers(self) -> List[str]:
        """List available provider names.
        
        Returns:
            List of provider names
        """
        return self.registry.list_providers()

    async def get_provider_health(self, provider_name: str) -> Dict[str, Any]:
        """Get health status of a provider.
        
        Args:
            provider_name: Name of the provider
            
        Returns:
            Dict with health information
        """
        provider = self.registry.get_provider(provider_name)
        if not provider:
            return {"healthy": False, "error": f"Provider not found: {provider_name}"}
        
        try:
            healthy = await provider.healthcheck()
            return {"healthy": healthy, "provider": provider_name}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def healthcheck_all(self) -> Dict[str, bool]:
        """Check health of all providers.
        
        Returns:
            Dict mapping provider names to health status
        """
        return await self.registry.healthcheck_all()

    async def list_models(self, provider_name: str = None) -> List[ModelInfo]:
        """List available models from a provider.
        
        Args:
            provider_name: Optional provider name (uses default if not specified)
            
        Returns:
            List of ModelInfo objects
        """
        provider = self.registry.get_provider(provider_name)
        if not provider:
            return []
        
        try:
            models = await provider.list_models()
            return [
                ModelInfo(
                    id=m.id,
                    name=m.name,
                    provider=m.provider.value if hasattr(m.provider, 'value') else str(m.provider),
                    context_length=m.context_length,
                    supports_streaming=m.supports_streaming,
                )
                for m in models
            ]
        except Exception as e:
            return []

    async def get_capabilities(self, provider_name: str) -> ProviderCapabilities:
        """Get capabilities of a provider.
        
        Args:
            provider_name: Name of the provider
            
        Returns:
            ProviderCapabilities object
        """
        provider = self.registry.get_provider(provider_name)
        if not provider:
            return ProviderCapabilities()
        
        try:
            caps = await provider.capabilities()
            return ProviderCapabilities(
                streaming=caps.streaming,
                function_calling=caps.function_calling,
                vision=caps.vision,
                embeddings=caps.embeddings,
                voice=caps.voice,
                stt=caps.stt,
                tts=caps.tts,
            )
        except Exception:
            return ProviderCapabilities()

    async def chat_once(self, request: ChatRequest) -> ChatResponse:
        """Perform a non-streaming chat completion.
        
        Args:
            request: ChatRequest with messages and settings
            
        Returns:
            ChatResponse with the completion
        """
        provider = self.registry.get_provider(request.provider)
        if not provider:
            raise ValueError(f"Provider not found: {request.provider}")
        
        # Convert to provider format
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        
        try:
            # Provider-specific chat_once call
            response = await provider.chat_once(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
                top_p=request.top_p,
                max_tokens=request.max_tokens,
                system_prompt=request.system_prompt,
            )
            return ChatResponse(
                content=response.get("content", ""),
                provider=request.provider or self.registry.default_provider,
                model=response.get("model", request.model or ""),
                tokens_prompt=response.get("tokens_prompt"),
                tokens_completion=response.get("tokens_completion"),
                finish_reason=response.get("finish_reason"),
            )
        except Exception as e:
            raise RuntimeError(f"Chat completion failed: {e}")

    async def chat_stream(
        self, 
        request: ChatRequest
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Perform a streaming chat completion.
        
        Args:
            request: ChatRequest with messages and settings
            
        Yields:
            Dict containing chunk data
        """
        provider = self.registry.get_provider(request.provider)
        if not provider:
            raise ValueError(f"Provider not found: {request.provider}")
        
        # Convert to provider format
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        
        try:
            async for chunk in provider.chat_stream(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
                top_p=request.top_p,
                max_tokens=request.max_tokens,
                system_prompt=request.system_prompt,
            ):
                yield chunk
        except Exception as e:
            yield {"error": str(e)}

    def get_default_provider(self) -> Optional[str]:
        """Get the default provider name.
        
        Returns:
            Default provider name or None
        """
        return self.registry.default_provider

    async def aclose(self) -> None:
        """Close all provider connections."""
        if self._registry:
            await self._registry.aclose()
