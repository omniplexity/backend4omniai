from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx
from fastapi import HTTPException

from backend.app.providers.base import Provider
from backend.app.providers.types import ModelInfo, ProviderCapabilities, ProviderHealth, StreamEvent


class OpenAICompatProvider(Provider):
    def __init__(
        self,
        provider_id: str,
        display_name: str,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: int = 120,
        client: httpx.AsyncClient | None = None,
    ):
        self.provider_id = provider_id
        self.display_name = display_name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.AsyncClient(timeout=self.timeout_seconds)
        self._logger = logging.getLogger("backend")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _map_error(self, exc: Exception, context: dict | None = None) -> None:
        if isinstance(exc, httpx.ConnectError):
            raise HTTPException(
                status_code=503,
                detail={"code": "PROVIDER_UNREACHABLE", "message": "Provider is unreachable"},
            )
        elif isinstance(exc, httpx.ReadTimeout):
            raise HTTPException(
                status_code=504,
                detail={"code": "PROVIDER_TIMEOUT", "message": "Provider request timed out"},
            )
        elif isinstance(exc, httpx.HTTPStatusError):
            self._log_http_error(exc, context)
            if exc.response.status_code == 429:
                raise HTTPException(
                    status_code=429,
                    detail={"code": "RATE_LIMITED", "message": "Provider rate limit exceeded"},
                )
            elif exc.response.status_code == 404:
                # Check if response mentions model not found
                try:
                    data = exc.response.json()
                    if "model" in str(data).lower() and ("not found" in str(data).lower() or "does not exist" in str(data).lower()):
                        raise HTTPException(
                            status_code=400,
                            detail={"code": "MODEL_NOT_FOUND", "message": "Requested model not found"},
                        )
                except Exception:
                    pass
            raise HTTPException(
                status_code=502,
                detail={"code": "PROVIDER_ERROR", "message": "Provider returned an error"},
            )
        else:
            raise HTTPException(
                status_code=502,
                detail={"code": "PROVIDER_ERROR", "message": "Provider communication failed"},
            )

    def _log_http_error(self, exc: httpx.HTTPStatusError, context: dict | None) -> None:
        response = exc.response
        status_code = response.status_code if response else None
        url = None
        if response:
            try:
                url = str(response.request.url)
            except Exception:
                url = str(response.url)

        body = None
        if response is not None:
            try:
                body = response.text
            except Exception:
                body = None
        if body:
            max_len = 2000
            if len(body) > max_len:
                body = f"{body[:max_len]}...(truncated)"

        context_str = json.dumps(context, ensure_ascii=False) if context else None

        self._logger.warning(
            "Provider HTTP error provider_id=%s status_code=%s url=%s body=%s request=%s",
            self.provider_id,
            status_code,
            url,
            body,
            context_str,
        )

    def _summarize_request(self, req: dict) -> dict:
        summary: dict = {
            "model": req.get("model"),
            "stream": req.get("stream"),
        }
        if "temperature" in req:
            summary["temperature"] = req.get("temperature")
        if "top_p" in req:
            summary["top_p"] = req.get("top_p")
        if "max_tokens" in req:
            summary["max_tokens"] = req.get("max_tokens")

        messages = req.get("messages") or []
        if isinstance(messages, list):
            summary["messages_count"] = len(messages)
            roles = []
            total_chars = 0
            last_user_len = None
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role")
                if role and role not in roles:
                    roles.append(role)
                content = msg.get("content")
                if isinstance(content, str):
                    total_chars += len(content)
                    if role == "user":
                        last_user_len = len(content)
            if roles:
                summary["roles"] = roles
            summary["total_chars"] = total_chars
            if last_user_len is not None:
                summary["last_user_len"] = last_user_len

        return summary

    async def list_models(self) -> list[ModelInfo]:
        try:
            response = await self._client.get(f"{self.base_url}/models", headers=self._headers())
            response.raise_for_status()
            data = response.json()
            models = []
            for model_data in data.get("data", []):
                models.append(
                    ModelInfo(
                        id=model_data["id"],
                        label=model_data.get("id"),  # Use id as label if no owned_by
                        raw=model_data,
                    )
                )
            return models
        except Exception as exc:
            self._map_error(exc)
            return []  # Should not reach here

    async def chat_once(self, req: dict) -> dict:
        req["stream"] = False
        try:
            response = await self._client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=req,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            self._map_error(exc, self._summarize_request(req))
            return {}  # Should not reach here

    async def chat_stream(self, req: dict) -> AsyncIterator[StreamEvent]:
        req["stream"] = True
        try:
            async with self._client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=req,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]  # Remove "data: "
                    if data == "[DONE]":
                        yield StreamEvent(type="done")
                        break
                    try:
                        chunk = json.loads(data)
                        if "choices" in chunk and chunk["choices"]:
                            choice = chunk["choices"][0]
                            if "delta" in choice and "content" in choice["delta"]:
                                yield StreamEvent(type="delta", delta=choice["delta"]["content"])
                        if "usage" in chunk:
                            yield StreamEvent(type="usage", usage=chunk["usage"])
                    except json.JSONDecodeError:
                        continue
        except Exception as exc:
            self._map_error(exc, self._summarize_request(req))

    async def healthcheck(self) -> ProviderHealth:
        try:
            await self.list_models()
            return ProviderHealth(ok=True)
        except Exception as exc:
            detail = str(exc.detail.get("message", "Unknown error")) if hasattr(exc, "detail") else str(exc)
            return ProviderHealth(ok=False, detail=detail)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            streaming=True,
            vision=False,  # Assume no vision for now
            tools=False,  # Assume no tools for now
            json_mode=False,  # Assume no json_mode for now
            max_context_tokens=None,  # Unknown
        )
