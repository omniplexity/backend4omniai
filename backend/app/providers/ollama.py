"""Ollama native provider adapter."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core import ProviderBadResponseError, get_logger
from app.providers.base import (
    BaseProvider,
    ChatChunk,
    ChatMessage,
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


class OllamaProvider(BaseProvider):
    """Adapter for Ollama's native HTTP API."""

    provider_type = ProviderType.OLLAMA

    def __init__(
        self,
        base_url: str,
        timeout: int,
        max_retries: int,
        transport: httpx.BaseTransport | None = None,
    ):
        self.display_name = "Ollama"
        self.max_retries = max_retries
        self.client = create_http_client(
            base_url=base_url,
            timeout_seconds=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def healthcheck(self) -> bool:
        """Check provider health using version endpoint, with tags fallback."""
        try:
            response = await request_with_retries(
                self.client, "GET", "/api/version", max_retries=self.max_retries
            )
            if response.status_code == 404:
                response = await request_with_retries(
                    self.client, "GET", "/api/tags", max_retries=self.max_retries
                )
            raise_for_status(response)
            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Ollama healthcheck failed",
                data={"error": str(exc), "provider": self.provider_type.value},
            )
            return False

    async def list_models(self) -> list[ModelInfo]:
        """List models from /api/tags."""
        response = await request_with_retries(
            self.client, "GET", "/api/tags", max_retries=self.max_retries
        )
        raise_for_status(response)
        payload = parse_json(response)

        models_payload = payload.get("models")
        if not isinstance(models_payload, list):
            raise ProviderBadResponseError(
                "Provider returned invalid response", details={"body": payload}
            )

        models: list[ModelInfo] = []
        for item in models_payload:
            model_id = item.get("name")
            if not model_id:
                continue
            metadata = {k: v for k, v in item.items() if k != "name"}
            models.append(
                ModelInfo(
                    id=model_id,
                    name=model_id,
                    provider=self.provider_type,
                    supports_streaming=True,
                    metadata=metadata,
                )
            )
        return models

    async def capabilities(self, _model: str | None = None) -> ProviderCapabilities:
        """Return conservative default capabilities for Ollama."""
        return ProviderCapabilities(
            streaming=True,
            function_calling=False,
            vision=False,
            embeddings=False,
        )

    async def chat_once(self, request: ChatRequest) -> ChatResponse:
        """Send a single chat request (non-streaming)."""
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": _format_messages(request.messages),
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.stop:
            payload["stop"] = request.stop
        if request.max_tokens is not None:
            payload["num_predict"] = request.max_tokens
        if request.top_p is not None:
            payload["top_p"] = request.top_p

        response = await request_with_retries(
            self.client,
            "POST",
            "/api/chat",
            json=payload,
            max_retries=self.max_retries,
        )
        raise_for_status(response)
        data = parse_json(response)

        message = (data.get("message") or {}).get("content")
        if message is None:
            raise ProviderBadResponseError(
                "Provider returned invalid response", details={"body": data}
            )

        finish_reason = data.get("done_reason") or ("stop" if data.get("done") else None)

        return ChatResponse(
            content=message,
            model=data.get("model", request.model),
            finish_reason=finish_reason or "stop",
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
            total_tokens=None,
        )

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        """Stream chat responses as JSON lines."""
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": _format_messages(request.messages),
            "stream": True,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.stop:
            payload["stop"] = request.stop
        if request.max_tokens is not None:
            payload["num_predict"] = request.max_tokens
        if request.top_p is not None:
            payload["top_p"] = request.top_p

        stream = await stream_with_retries(
            self.client,
            "POST",
            "/api/chat",
            json=payload,
            max_retries=self.max_retries,
        )

        async with stream:
            raise_for_status(stream)
            async for line in stream.aiter_lines():
                if not line:
                    continue
                try:
                    chunk_obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ProviderBadResponseError(
                        "Provider returned invalid response", details={"body": line}
                    ) from exc

                content = (chunk_obj.get("message") or {}).get("content") or ""
                finish_reason = (
                    chunk_obj.get("done_reason")
                    if chunk_obj.get("done")
                    else chunk_obj.get("finish_reason")
                )

                if not content and not finish_reason:
                    continue

                yield ChatChunk(
                    content=content,
                    finish_reason=finish_reason,
                    model=chunk_obj.get("model", request.model),
                )

                if chunk_obj.get("done"):
                    break


def _format_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
    """Convert ChatMessage objects to Ollama's expected shape."""
    return [{"role": msg.role, "content": msg.content} for msg in messages]
