"""Tests for provider registry and adapters (Phase 4)."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.core import (
    ErrorCode,
    ProviderAuthError,
    ProviderUnavailableError,
    RateLimitError,
)
from app.main import create_app
from app.providers import OllamaProvider, OpenAICompatProvider, ProviderRegistry


@pytest.mark.asyncio
async def test_registry_loads_enabled_providers() -> None:
    """Registry instantiates enabled providers from settings."""
    settings = Settings(
        provider_default="lmstudio",
        providers_enabled="lmstudio,ollama",
        lmstudio_base_url="http://lmstudio.test",
        ollama_base_url="http://ollama.test",
        provider_timeout_seconds=5,
        provider_max_retries=0,
    )

    registry = ProviderRegistry(
        settings,
        transport_overrides={
            "lmstudio": httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []})),
            "ollama": httpx.MockTransport(lambda request: httpx.Response(200, json={"models": []})),
        },
    )

    assert set(registry.providers.keys()) == {"lmstudio", "ollama"}
    await registry.aclose()


@pytest.mark.asyncio
async def test_openai_compat_list_models_parses_response() -> None:
    """OpenAI-compatible adapter parses /v1/models correctly."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"data": [{"id": "gpt-test"}, {"id": "gpt-extra"}]}
        )
    )
    provider = OpenAICompatProvider(
        base_url="http://openai.test",
        timeout=5,
        max_retries=0,
        api_key="test-key",
        transport=transport,
    )

    models = await provider.list_models()

    assert [model.id for model in models] == ["gpt-test", "gpt-extra"]
    await provider.aclose()


@pytest.mark.asyncio
async def test_ollama_list_models_parses_response() -> None:
    """Ollama adapter parses /api/tags response."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"models": [{"name": "llama2"}, {"name": "mistral"}]}
        )
    )
    provider = OllamaProvider(
        base_url="http://ollama.test",
        timeout=5,
        max_retries=0,
        transport=transport,
    )

    models = await provider.list_models()
    assert [model.id for model in models] == ["llama2", "mistral"]
    await provider.aclose()


@pytest.mark.asyncio
async def test_error_mapping_timeout_maps_to_provider_unavailable() -> None:
    """Network timeouts map to provider_unavailable."""
    def handler(_request: httpx.Request) -> httpx.Response:  # noqa: ANN001
        raise httpx.ReadTimeout("timeout")

    provider = OpenAICompatProvider(
        base_url="http://timeout.test",
        timeout=1,
        max_retries=0,
        api_key=None,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderUnavailableError) as exc:
        await provider.list_models()

    assert exc.value.code == ErrorCode.PROVIDER_UNAVAILABLE
    await provider.aclose()


@pytest.mark.asyncio
async def test_error_mapping_401_maps_to_provider_auth_failed() -> None:
    """401/403 map to provider_auth_failed."""
    provider = OpenAICompatProvider(
        base_url="http://auth.test",
        timeout=1,
        max_retries=0,
        api_key=None,
        transport=httpx.MockTransport(lambda request: httpx.Response(401, json={})),
    )

    with pytest.raises(ProviderAuthError) as exc:
        await provider.list_models()

    assert exc.value.code == ErrorCode.PROVIDER_AUTH_FAILED
    await provider.aclose()


@pytest.mark.asyncio
async def test_error_mapping_429_maps_to_rate_limited() -> None:
    """429 maps to rate_limited code."""
    provider = OpenAICompatProvider(
        base_url="http://ratelimit.test",
        timeout=1,
        max_retries=0,
        api_key=None,
        transport=httpx.MockTransport(lambda request: httpx.Response(429, json={})),
    )

    with pytest.raises(RateLimitError) as exc:
        await provider.list_models()

    assert exc.value.code == ErrorCode.RATE_LIMITED
    await provider.aclose()


def test_provider_endpoints_return_shapes_and_request_id() -> None:
    """Provider endpoints expose expected shapes with X-Request-ID headers."""

    def lmstudio_handler(request: httpx.Request) -> httpx.Response:  # noqa: ANN001
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "lmstudio-test"}]})
        return httpx.Response(404)

    def ollama_handler(request: httpx.Request) -> httpx.Response:  # noqa: ANN001
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.1.0"})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "ollama-test"}]})
        return httpx.Response(404)

    settings = Settings(
        provider_default="lmstudio",
        providers_enabled="lmstudio,ollama",
        lmstudio_base_url="http://lmstudio.test",
        ollama_base_url="http://ollama.test",
        provider_timeout_seconds=5,
        provider_max_retries=0,
    )

    registry = ProviderRegistry(
        settings,
        transport_overrides={
            "lmstudio": httpx.MockTransport(lmstudio_handler),
            "ollama": httpx.MockTransport(ollama_handler),
        },
    )

    app = create_app()
    app.state.provider_registry = registry

    with TestClient(app) as client:
        providers_resp = client.get("/providers")
        assert providers_resp.status_code == 200
        assert "X-Request-ID" in providers_resp.headers
        providers = providers_resp.json()
        assert isinstance(providers, list)
        assert providers[0]["id"] == "lmstudio"
        assert "ok" in providers[0]

        models_resp = client.get("/providers/lmstudio/models")
        assert models_resp.status_code == 200
        assert "X-Request-ID" in models_resp.headers
        assert models_resp.json() == ["lmstudio-test"]

    asyncio.run(registry.aclose())
