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
    voice: bool = False
    stt: bool = False
    tts: bool = False
    voices: bool = False


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

    async def supports_voice(self) -> bool:
        """Check if provider supports any voice features."""
        caps = await self.capabilities()
        return caps.voice or caps.stt or caps.tts or caps.voices

    async def supports_stt(self) -> bool:
        """Check if provider supports speech-to-text."""
        caps = await self.capabilities()
        return caps.stt

    async def supports_tts(self) -> bool:
        """Check if provider supports text-to-speech."""
        caps = await self.capabilities()
        return caps.tts

    async def supports_voices(self) -> bool:
        """Check if provider supports voice listing."""
        caps = await self.capabilities()
        return caps.voices

    async def embed_texts(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Providers that support embeddings should override this method.
        """
        raise NotImplementedError("Embeddings not supported by this provider")

    async def start_stt(self, language: str = "en-US", interim_results: bool = True, continuous: bool = True) -> AsyncIterator[dict]:
        """
        Start speech-to-text stream.

        Args:
            language: Language code for speech recognition
            interim_results: Whether to return interim results
            continuous: Whether to continue listening after speech ends

        Yields:
            Dictionary with transcript results

        Raises:
            NotImplementedError: If provider doesn't support STT
        """
        raise NotImplementedError("Speech-to-text not supported by this provider")

    async def text_to_speech(self, text: str, voice_id: str | None = None, speed: float = 1.0, pitch: float = 1.0, volume: float = 1.0) -> bytes:
        """
        Convert text to speech.

        Args:
            text: Text to convert to speech
            voice_id: Voice ID to use (optional)
            speed: Speech speed (0.5-2.0)
            pitch: Speech pitch (0.5-2.0)
            volume: Speech volume (0.0-1.0)

        Returns:
            Audio data as bytes

        Raises:
            NotImplementedError: If provider doesn't support TTS
        """
        raise NotImplementedError("Text-to-speech not supported by this provider")

    async def list_voices(self) -> list[dict]:
        """
        List available voices.

        Returns:
            List of voice dictionaries with id, name, language, gender

        Raises:
            NotImplementedError: If provider doesn't support voice listing
        """
        raise NotImplementedError("Voice listing not supported by this provider")
