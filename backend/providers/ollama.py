"""Ollama provider implementation."""

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


class OllamaProvider(BaseProvider):
    """Provider for Ollama local LLM server."""

    provider_type = ProviderType.OLLAMA

    def __init__(self, base_url: str, timeout: int = 30):
        """Initialize Ollama provider."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def aclose(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def healthcheck(self) -> bool:
        """Check if Ollama is available."""
        try:
            response = await self.client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> List[ModelInfo]:
        """List available models from Ollama."""
        try:
            response = await self.client.get("/api/tags")
            response.raise_for_status()
            data = response.json()

            models = []
            for model in data.get("models", []):
                models.append(ModelInfo(
                    id=model.get("name", "unknown"),
                    name=model.get("name", "unknown"),
                    provider=self.provider_type,
                    metadata={
                        "size": model.get("size"),
                        "modified_at": model.get("modified_at"),
                    },
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
            "stream": False,
            "options": {
                "temperature": request.temperature,
            },
        }

        if request.max_tokens:
            payload["options"]["num_predict"] = request.max_tokens

        response = await self.client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

        return ChatResponse(
            content=data["message"]["content"],
            model=data.get("model", request.model),
            finish_reason="stop",
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
        )

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        """Stream chat response."""
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        payload = {
            "model": request.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": request.temperature,
            },
        }

        if request.max_tokens:
            payload["options"]["num_predict"] = request.max_tokens

        async with self.client.stream(
            "POST",
            "/api/chat",
            json=payload,
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line:
                    continue

                try:
                    data = json.loads(line)

                    if data.get("done"):
                        yield ChatChunk(
                            content="",
                            finish_reason="stop",
                            model=data.get("model"),
                        )
                        break

                    if "message" in data and "content" in data["message"]:
                        yield ChatChunk(
                            content=data["message"]["content"],
                            finish_reason=None,
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
            model=model or "llama2",
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens"),
        )

        async for chunk in self.chat_stream(request):
            yield {"content": chunk.content, "finish_reason": chunk.finish_reason}

    async def capabilities(self, model: str | None = None) -> ProviderCapabilities:
        """Get Ollama capabilities with voice support."""
        return ProviderCapabilities(
            streaming=True,
            function_calling=False,
            vision=False,  # Some Ollama models support vision
            embeddings=True,
            voice=True,    # Ollama supports voice through extensions
            stt=True,      # Speech-to-text via extensions
            tts=True,      # Text-to-speech via extensions
            voices=True,   # Voice listing via extensions
        )

    async def start_stt(self, language: str = "en-US", interim_results: bool = True, continuous: bool = True) -> AsyncIterator[dict]:
        """
        Start speech-to-text stream using Ollama's voice extension.
        
        Note: This requires Ollama to have voice extensions installed.
        """
        try:
            # Check if voice extension is available
            response = await self.client.get("/api/voice/models")
            if response.status_code != 200:
                raise NotImplementedError("Voice extension not available")
            
            # Start STT stream
            payload = {
                "language": language,
                "interim_results": interim_results,
                "continuous": continuous
            }
            
            async with self.client.stream(
                "POST",
                "/api/voice/stt",
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
                        yield {
                            "final": data.get("final"),
                            "interim": data.get("interim"),
                            "is_final": data.get("is_final", False),
                            "confidence": data.get("confidence")
                        }
                    except json.JSONDecodeError:
                        continue
                        
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise NotImplementedError("Voice extension not installed on Ollama server")
            raise
        except Exception as e:
            raise NotImplementedError(f"Speech-to-text not available: {e}")

    async def text_to_speech(self, text: str, voice_id: str | None = None, speed: float = 1.0, pitch: float = 1.0, volume: float = 1.0) -> bytes:
        """
        Convert text to speech using Ollama's voice extension.
        """
        try:
            payload = {
                "text": text,
                "voice_id": voice_id,
                "speed": speed,
                "pitch": pitch,
                "volume": volume
            }
            
            response = await self.client.post("/api/voice/tts", json=payload)
            response.raise_for_status()
            
            return response.content
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise NotImplementedError("Voice extension not installed on Ollama server")
            raise
        except Exception as e:
            raise NotImplementedError(f"Text-to-speech not available: {e}")

    async def list_voices(self) -> list[dict]:
        """
        List available voices using Ollama's voice extension.
        """
        try:
            response = await self.client.get("/api/voice/voices")
            response.raise_for_status()
            
            data = response.json()
            return data.get("voices", [])
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise NotImplementedError("Voice extension not installed on Ollama server")
            raise
        except Exception as e:
            raise NotImplementedError(f"Voice listing not available: {e}")

    async def embed_texts(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """Generate embeddings using Ollama embed endpoints (best-effort).

        Ollama has historically exposed embedding endpoints. Since variants exist,
        we try a couple of common shapes.
        """
        if not texts:
            return []

        if not model:
            # Caller should set an embeddings model; defaulting here is risky.
            raise ValueError("Ollama embeddings require an explicit model")

        # 1) Try batch endpoint: /api/embed {model, input:[...]}
        try:
            resp = await self.client.post("/api/embed", json={"model": model, "input": texts})
            if resp.status_code == 200:
                data = resp.json()
                embeddings = data.get("embeddings")
                if isinstance(embeddings, list):
                    return embeddings
        except Exception:
            pass

        # 2) Fallback: per-text /api/embeddings {model, prompt:text}
        results: list[list[float]] = []
        for t in texts:
            resp = await self.client.post("/api/embeddings", json={"model": model, "prompt": t})
            resp.raise_for_status()
            data = resp.json()
            emb = data.get("embedding")
            if not isinstance(emb, list):
                emb = []
            results.append(emb)
        return results
