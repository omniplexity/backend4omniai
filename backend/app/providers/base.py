"""
Base provider interface.

Defines the contract that all AI providers must implement.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProviderType(str, Enum):
    """Supported provider types."""

    LMSTUDIO = "lmstudio"
    OLLAMA = "ollama"
    OPENAI_COMPAT = "openai_compat"


@dataclass
class ModelInfo:
    """Information about an available model."""

    id: str
    name: str
    provider: ProviderType
    context_length: int | None = None
    supports_streaming: bool = True
    supports_functions: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderCapabilities:
    """Capabilities of a provider."""

    streaming: bool = True
    function_calling: bool = False
    vision: bool = False
    embeddings: bool = False


@dataclass
class ChatMessage:
    """A single chat message."""

    role: str  # "system", "user", "assistant"
    content: str
    name: str | None = None


@dataclass
class ChatRequest:
    """Request for chat completion."""

    messages: list[ChatMessage]
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None
    top_p: float | None = None
    stream: bool = True
    stop: list[str] | None = None


@dataclass
class ChatChunk:
    """A single chunk from streaming response."""

    content: str
    finish_reason: str | None = None
    model: str | None = None


@dataclass
class ChatResponse:
    """Complete chat response (non-streaming)."""

    content: str
    model: str
    finish_reason: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


# Alias used by future streaming interfaces
StreamChunk = ChatChunk


class BaseProvider(ABC):
    """
    Abstract base class for AI providers.

    All providers must implement this interface to ensure consistent
    behavior across LM Studio, Ollama, and OpenAI-compatible endpoints.
    """

    provider_type: ProviderType

    async def aclose(self) -> None:
        """Close any underlying resources (optional)."""
        return None

    @abstractmethod
    async def healthcheck(self) -> bool:
        """
        Check if the provider is available and responding.

        Returns:
            True if provider is healthy, False otherwise
        """
        ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """
        List all available models from this provider.

        Returns:
            List of ModelInfo objects describing available models
        """
        ...

    @abstractmethod
    async def capabilities(self, model: str | None = None) -> ProviderCapabilities:
        """
        Get the capabilities of this provider.

        Returns:
            ProviderCapabilities object
        """
        ...

    @abstractmethod
    async def chat_once(self, request: ChatRequest) -> ChatResponse:
        """
        Send a chat request and wait for complete response.

        Args:
            request: ChatRequest with messages and parameters

        Returns:
            Complete ChatResponse

        Raises:
            ProviderError: If the provider returns an error
            ProviderUnavailableError: If the provider is not available
        """
        ...

    @abstractmethod
    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        """
        Send a chat request and stream the response.

        Args:
            request: ChatRequest with messages and parameters

        Yields:
            ChatChunk objects as they arrive

        Raises:
            ProviderError: If the provider returns an error
            ProviderUnavailableError: If the provider is not available
        """
        ...
