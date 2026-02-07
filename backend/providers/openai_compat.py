"""OpenAI-compatible provider implementation."""

from collections.abc import AsyncIterator
from typing import Any, Dict, List
import json

import httpx

from backend.providers.base import (
    BaseProvider,
    ChatChunk,
    ChatRequest,
    ChatResponse,
    ModelInfo,
    ProviderCapabilities,
    ProviderType,
)


class OpenAICompatProvider(BaseProvider):
    """Provider for OpenAI-compatible endpoints."""

    provider_type = ProviderType.OPENAI_COMPAT

    def __init__(self, base_url: str, api_key: str = "", timeout: int = 30):
        """Initialize OpenAI-compatible provider."""
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=headers,
            )
        return self._client

    async def aclose(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def healthcheck(self) -> bool:
        """Check if endpoint is available."""
        try:
            response = await self.client.get("/models")
            return response.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> List[ModelInfo]:
        """List available models."""
        try:
            response = await self.client.get("/models")
            response.raise_for_status()
            data = response.json()

            models = []
            for model in data.get("data", []):
                models.append(ModelInfo(
                    id=model.get("id", "unknown"),
                    name=model.get("id", "unknown"),
                    provider=self.provider_type,
                ))
            return models
        except Exception:
            return []

    async def chat_once(self, request: ChatRequest) -> ChatResponse:
        """Send non-streaming chat request."""
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "stream": False,
        }

        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if request.top_p:
            payload["top_p"] = request.top_p
        if request.stop:
            payload["stop"] = request.stop

        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return ChatResponse(
            content=choice["message"]["content"],
            model=data.get("model", request.model),
            finish_reason=choice.get("finish_reason", "stop"),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        """Stream chat response."""
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "stream": True,
        }

        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if request.top_p:
            payload["top_p"] = request.top_p
        if request.stop:
            payload["stop"] = request.stop

        async with self.client.stream(
            "POST",
            "/chat/completions",
            json=payload,
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                    choice = data["choices"][0]
                    delta = choice.get("delta", {})

                    if "content" in delta:
                        yield ChatChunk(
                            content=delta["content"],
                            finish_reason=choice.get("finish_reason"),
                            model=data.get("model"),
                        )
                except json.JSONDecodeError:
                    continue

    async def stream_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str = None,
        **kwargs,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream completion with simpler interface for ChatService."""
        from backend.providers.base import ChatMessage

        chat_messages = [
            ChatMessage(role=m["role"], content=m["content"])
            for m in messages
        ]

        request = ChatRequest(
            messages=chat_messages,
            model=model or "gpt-3.5-turbo",
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens"),
        )

        async for chunk in self.chat_stream(request):
            yield {"content": chunk.content, "finish_reason": chunk.finish_reason}

    async def capabilities(self, model: str | None = None) -> ProviderCapabilities:
        """Get OpenAI-compatible capabilities with voice support."""
        return ProviderCapabilities(
            streaming=True,
            function_calling=True,
            vision=False,
            embeddings=True,
            voice=True,    # OpenAI supports voice features
            stt=False,     # STT not implemented (requires audio upload, not streaming)
            tts=True,      # Text-to-speech via TTS models
            voices=True,   # Voice listing available
        )

    async def start_stt(self, language: str = "en-US", interim_results: bool = True, continuous: bool = True) -> AsyncIterator[dict]:
        """
        Start speech-to-text stream using OpenAI's Whisper API.
        """
        try:
            # Note: OpenAI's Whisper API is not streaming, so we simulate it
            # This would need to be implemented based on the specific OpenAI-compatible endpoint
            raise NotImplementedError("Streaming STT not implemented for OpenAI-compatible providers")
            
        except Exception as e:
            raise NotImplementedError(f"Speech-to-text not available: {e}")

    async def text_to_speech(self, text: str, voice_id: str | None = None, speed: float = 1.0, pitch: float = 1.0, volume: float = 1.0) -> bytes:
        """
        Convert text to speech using OpenAI's TTS API.
        """
        try:
            payload = {
                "model": "tts-1" if not voice_id or "hd" not in voice_id else "tts-1-hd",
                "voice": voice_id or "alloy",
                "input": text,
            }
            
            response = await self.client.post("/audio/speech", json=payload)
            response.raise_for_status()
            
            return response.content
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise NotImplementedError("TTS not available on this endpoint")
            raise
        except Exception as e:
            raise NotImplementedError(f"Text-to-speech not available: {e}")

    async def list_voices(self) -> list[dict]:
        """
        List available voices for OpenAI-compatible TTS.
        """
        try:
            # OpenAI doesn't have a standard voices endpoint, so we return common ones
            return [
                {"id": "alloy", "name": "Alloy", "language": "en-US", "gender": "Neutral"},
                {"id": "echo", "name": "Echo", "language": "en-US", "gender": "Male"},
                {"id": "fable", "name": "Fable", "language": "en-US", "gender": "Female"},
                {"id": "onyx", "name": "Onyx", "language": "en-US", "gender": "Male"},
                {"id": "nova", "name": "Nova", "language": "en-US", "gender": "Female"},
                {"id": "shimmer", "name": "Shimmer", "language": "en-US", "gender": "Female"},
                # HD variants
                {"id": "alloy-hd", "name": "Alloy HD", "language": "en-US", "gender": "Neutral"},
                {"id": "echo-hd", "name": "Echo HD", "language": "en-US", "gender": "Male"},
                {"id": "fable-hd", "name": "Fable HD", "language": "en-US", "gender": "Female"},
                {"id": "onyx-hd", "name": "Onyx HD", "language": "en-US", "gender": "Male"},
                {"id": "nova-hd", "name": "Nova HD", "language": "en-US", "gender": "Female"},
                {"id": "shimmer-hd", "name": "Shimmer HD", "language": "en-US", "gender": "Female"},
            ]
            
        except Exception as e:
            raise NotImplementedError(f"Voice listing not available: {e}")

    async def embed_texts(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """Generate embeddings using OpenAI-compatible /embeddings endpoint."""
        if not texts:
            return []

        payload = {
            "input": texts,
        }
        if model:
            payload["model"] = model

        response = await self.client.post("/embeddings", json=payload)
        response.raise_for_status()
        data = response.json()

        items = data.get("data", [])
        # Expect order preserved. If not, best-effort sort by index.
        if items and isinstance(items[0], dict) and "index" in items[0]:
            items = sorted(items, key=lambda x: x.get("index", 0))

        return [it.get("embedding", []) for it in items]
