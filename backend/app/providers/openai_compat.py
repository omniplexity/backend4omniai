"""
OpenAI-compatible provider adapter.

Supports any endpoint that implements the OpenAI Chat Completions API surface.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core import ProviderBadResponseError, get_logger
from app.providers.base import (
    BaseProvider,
    ChatChunk,
    ChatRequest,
    ChatResponse,
    ModelInfo,
    ProviderCapabilities,
    ProviderType,
)
from app.providers.http_client import (
    create_http_client,
    parse_json,
    raise_for_status,
    request_with_retries,
    stream_with_retries,
)

logger = get_logger(__name__)


class OpenAICompatProvider(BaseProvider):
    """Adapter for OpenAI-compatible chat endpoints."""

    def __init__(
        self,
        base_url: str,
        timeout: int,
        max_retries: int,
        api_key: str | None = None,
        provider_type: ProviderType = ProviderType.OPENAI_COMPAT,
        display_name: str = "OpenAI Compatible",
        transport: httpx.BaseTransport | None = None,
    ):
        self.provider_type = provider_type
        self.display_name = display_name
        self.max_retries = max_retries

        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self.client = create_http_client(
            base_url=base_url,
            timeout_seconds=timeout,
            headers=headers,
            transport=transport,
        )

    async def aclose(self) -> None:
        """Close underlying HTTP resources."""
        await self.client.aclose()

    async def healthcheck(self) -> bool:
        """Ping models endpoint to confirm connectivity."""
        try:
            response = await request_with_retries(
                self.client, "GET", "/v1/models", max_retries=self.max_retries
            )
            raise_for_status(response)
            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "OpenAI-compatible healthcheck failed",
                data={"provider": self.provider_type.value, "error": str(exc)},
            )
            return False

    async def list_models(self) -> list[ModelInfo]:
        """Return available models."""
        response = await request_with_retries(
            self.client, "GET", "/v1/models", max_retries=self.max_retries
        )
        raise_for_status(response)
        payload = parse_json(response)

        data = payload.get("data")
        if not isinstance(data, list):
            raise ProviderBadResponseError(
                "Provider returned invalid response", details={"body": payload}
            )

        models: list[ModelInfo] = []
        for item in data:
            model_id = item.get("id")
            if not model_id:
                continue
            models.append(
                ModelInfo(
                    id=model_id,
                    name=model_id,
                    provider=self.provider_type,
                    supports_streaming=True,
                )
            )
        return models

    async def capabilities(self, _model: str | None = None) -> ProviderCapabilities:
        """Return conservative default capabilities."""
        return ProviderCapabilities(
            streaming=True,
            function_calling=False,
            vision=False,
            embeddings=False,
        )

    async def chat_once(self, request: ChatRequest) -> ChatResponse:
        """Send a non-streaming chat completion request."""
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [message.__dict__ for message in request.messages],
            "temperature": request.temperature,
            "stream": False,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop:
            payload["stop"] = request.stop

        response = await request_with_retries(
            self.client,
            "POST",
            "/v1/chat/completions",
            json=payload,
            max_retries=self.max_retries,
        )
        raise_for_status(response)

        data = parse_json(response)
        try:
            choice = data["choices"][0]
            message = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderBadResponseError(
                "Provider returned invalid response", details={"body": data}
            ) from exc

        usage = data.get("usage") or {}
        finish_reason = choice.get("finish_reason") or "stop"

        return ChatResponse(
            content=message or "",
            model=data.get("model", request.model),
            finish_reason=finish_reason,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        """Stream chat completions using SSE-style data lines."""
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [message.__dict__ for message in request.messages],
            "temperature": request.temperature,
            "stream": True,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop:
            payload["stop"] = request.stop

        stream = await stream_with_retries(
            self.client,
            "POST",
            "/v1/chat/completions",
            json=payload,
            max_retries=self.max_retries,
        )

        async with stream:
            raise_for_status(stream)
            async for line in stream.aiter_lines():
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    data_str = line.removeprefix("data:").strip()
                else:
                    data_str = line.strip()

                if data_str == "[DONE]":
                    break

                try:
                    chunk_obj = json.loads(data_str)
                except json.JSONDecodeError as exc:
                    raise ProviderBadResponseError(
                        "Provider returned invalid response", details={"body": data_str}
                    ) from exc

                choices = chunk_obj.get("choices") or []
                if not choices:
                    continue

                delta = choices[0].get("delta") or {}
                finish_reason = choices[0].get("finish_reason")
                content = delta.get("content") or ""

                yield ChatChunk(
                    content=content,
                    finish_reason=finish_reason,
                    model=chunk_obj.get("model", request.model),
                )
