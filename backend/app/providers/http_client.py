"""
Shared HTTP client helpers for provider adapters.

Provides consistent timeouts, retry behavior, and error mapping so provider
adapters return stable AppError instances without leaking stack traces.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.core import (
    ModelNotFoundError,
    ProviderAuthError,
    ProviderBadResponseError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
    get_logger,
    request_id_ctx,
)

logger = get_logger(__name__)


def create_http_client(
    base_url: str,
    timeout_seconds: int,
    headers: dict[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> httpx.AsyncClient:
    """
    Build an AsyncClient with consistent timeout settings.

    Args:
        base_url: Base URL for the provider.
        timeout_seconds: Total timeout for requests.
        headers: Default headers to include.
        transport: Optional transport (used by tests with MockTransport).
    """
    timeout = httpx.Timeout(
        timeout_seconds, connect=timeout_seconds, read=timeout_seconds, write=timeout_seconds
    )
    base = base_url.rstrip("/")
    return httpx.AsyncClient(
        base_url=base,
        timeout=timeout,
        headers=headers or {},
        transport=transport,
    )


async def request_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_retries: int,
    **kwargs: Any,
) -> httpx.Response:
    """
    Execute an HTTP request with lightweight retries and mapped errors.

    Retries are only applied to network/timeout errors, not HTTP status codes.
    """
    headers = kwargs.pop("headers", {}) or {}
    request_id = request_id_ctx.get()
    if request_id and "X-Request-ID" not in headers:
        headers["X-Request-ID"] = request_id
    kwargs["headers"] = headers

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await client.request(method, url, **kwargs)
        except (
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.NetworkError,
            httpx.TimeoutException,
        ) as exc:
            last_error = exc
            if attempt < max_retries:
                await asyncio.sleep(min(0.1 * (attempt + 1), 1.0))
                continue
            raise ProviderUnavailableError(
                "Provider unavailable", details={"reason": str(exc)}
            ) from exc
        except httpx.HTTPError as exc:  # Covers other request-level errors
            last_error = exc
            if attempt < max_retries:
                await asyncio.sleep(min(0.1 * (attempt + 1), 1.0))
                continue
            raise ProviderError("Provider request failed", details={"reason": str(exc)}) from exc

    # Fallback (should not be reached)
    raise ProviderUnavailableError(
        "Provider unavailable", details={"reason": str(last_error)}
    )


async def stream_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_retries: int,
    **kwargs: Any,
) -> httpx.Response:
    """
    Open a streaming request with the same retry semantics as request_with_retries.
    """
    headers = kwargs.pop("headers", {}) or {}
    request_id = request_id_ctx.get()
    if request_id and "X-Request-ID" not in headers:
        headers["X-Request-ID"] = request_id
    kwargs["headers"] = headers

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await client.stream(method, url, **kwargs)
        except (
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.NetworkError,
            httpx.TimeoutException,
        ) as exc:
            last_error = exc
            if attempt < max_retries:
                await asyncio.sleep(min(0.1 * (attempt + 1), 1.0))
                continue
            raise ProviderUnavailableError(
                "Provider unavailable", details={"reason": str(exc)}
            ) from exc
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt < max_retries:
                await asyncio.sleep(min(0.1 * (attempt + 1), 1.0))
                continue
            raise ProviderError("Provider request failed", details={"reason": str(exc)}) from exc

    raise ProviderUnavailableError(
        "Provider unavailable", details={"reason": str(last_error)}
    )


def raise_for_status(response: httpx.Response) -> None:
    """
    Map HTTP status codes to stable AppError types.
    """
    status = response.status_code
    if status < 400:
        return

    details = _safe_error_details(response)

    if status in (401, 403):
        raise ProviderAuthError(details=details, status_code=status)
    if status == 404:
        raise ModelNotFoundError(details=details)
    if status == 429:
        raise RateLimitError("Rate limit exceeded", details=details)
    if status >= 500:
        raise ProviderUnavailableError("Provider unavailable", details=details)
    raise ProviderError("Provider error", details=details)


def parse_json(response: httpx.Response) -> Any:
    """
    Parse JSON with consistent error handling.
    """
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        snippet = response.text[:500] if response.text else ""
        raise ProviderBadResponseError(
            "Provider returned invalid response",
            details={"body": snippet},
        ) from exc


def _safe_error_details(response: httpx.Response) -> dict[str, Any]:
    """Return a small, non-sensitive error payload for debugging."""
    body_snippet = ""
    try:
        if response.text:
            body_snippet = response.text[:300]
    except Exception:  # pragma: no cover - defensive
        body_snippet = ""

    return {
        "status": response.status_code,
        "body": body_snippet,
        "url": str(response.url),
    }
