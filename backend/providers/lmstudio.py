"""LM Studio provider implementation."""

from collections.abc import AsyncIterator
from typing import Any, Dict, List

import httpx

from backend.providers.base import (
    BaseProvider,
    ChatChunk,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ModelInfo,
    ProviderCapabilities,
    ProviderType,
)


class LMStudioProvider(BaseProvider):
    """Provider for LM Studio (OpenAI-compatible local server)."""

    provider_type = ProviderType.LMSTUDIO

    def __init__(self, base_url: str, timeout: int = 30):
        """Initialize LM Studio provider."""
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
        """Check if LM Studio is available."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.debug(f"Healthcheck: Connecting to LM Studio at {self.base_url}/v1/models")
            response = await self.client.get("/v1/models")
            is_healthy = response.status_code == 200
            if is_healthy:
                logger.debug(f"Healthcheck: LM Studio is healthy (status {response.status_code})")
            else:
                logger.warning(f"Healthcheck: LM Studio returned status {response.status_code}")
            return is_healthy
        except httpx.ConnectError as e:
            logger.error(f"Healthcheck: Cannot connect to LM Studio at {self.base_url}: {e}")
            return False
        except Exception as e:
            logger.error(f"Healthcheck: LM Studio check failed: {type(e).__name__}: {e}")
            return False

    async def list_models(self) -> List[ModelInfo]:
        """List available models from LM Studio."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"Fetching models from LM Studio at {self.base_url}/v1/models")
            response = await self.client.get("/v1/models")
            response.raise_for_status()
            data = response.json()
            
            logger.debug(f"LM Studio response: {data}")

            models = []
            models_data = data.get("data", [])
            
            if not models_data:
                logger.warning(f"LM Studio returned empty model list. Response: {data}")
                return []
            
            for model in models_data:
                model_id = model.get("id")
                if model_id:
                    models.append(ModelInfo(
                        id=model_id,
                        name=model.get("name") or model_id,
                        provider=self.provider_type,
                        context_length=model.get("context_length"),
                    ))
                else:
                    logger.warning(f"Skipping model with missing id: {model}")
                    
            logger.info(f"Successfully fetched {len(models)} models from LM Studio")
            return models
        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to LM Studio at {self.base_url}: {e}")
            return []
        except httpx.HTTPStatusError as e:
            logger.error(f"LM Studio returned error status {e.response.status_code}: {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"Failed to list models from LM Studio: {type(e).__name__}: {e}")
            return []

    async def capabilities(self, model: str | None = None) -> ProviderCapabilities:
        """Get LM Studio capabilities."""
        return ProviderCapabilities(
            streaming=True,
            function_calling=False,
            vision=False,
            embeddings=False,
        )

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

        response = await self.client.post("/v1/chat/completions", json=payload)
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
        import logging
        logger = logging.getLogger(__name__)
        
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

        logger.info(f"LM Studio chat_stream: connecting to {self.base_url}/v1/chat/completions with model {request.model}")
        
        try:
            async with self.client.stream(
                "POST",
                "/v1/chat/completions",
                json=payload,
            ) as response:
                response.raise_for_status()
                logger.info(f"LM Studio chat_stream: connection established, streaming response")
                
                chunk_count = 0
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:]  # Remove "data: " prefix
                    if data_str == "[DONE]":
                        logger.info(f"LM Studio chat_stream: received [DONE], total chunks: {chunk_count}")
                        break

                    import json
                    try:
                        data = json.loads(data_str)
                        choice = data["choices"][0]
                        delta = choice.get("delta", {})

                        if "content" in delta:
                            chunk_count += 1
                            yield ChatChunk(
                                content=delta["content"],
                                finish_reason=choice.get("finish_reason"),
                                model=data.get("model"),
                            )
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logger.error(f"LM Studio chat_stream: error processing chunk: {e}")
                        continue
        except Exception as e:
            logger.error(f"LM Studio chat_stream: stream failed: {type(e).__name__}: {e}")
            raise

    async def stream_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str = None,
        **kwargs,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream completion with simpler interface for ChatService."""
        chat_messages = [
            ChatMessage(role=m["role"], content=m["content"])
            for m in messages
        ]

        request = ChatRequest(
            messages=chat_messages,
            model=model or "default",
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens"),
        )

        async for chunk in self.chat_stream(request):
            yield {"content": chunk.content, "finish_reason": chunk.finish_reason}
