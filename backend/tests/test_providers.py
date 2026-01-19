import pytest
import httpx

from backend.app.main import app
from backend.app.config.settings import settings


@pytest.fixture
def authenticated_client(client):
    """Test client with authenticated admin user."""
    # Bootstrap admin
    response = client.post("/admin/bootstrap", json={
        "username": "admin",
        "password": "adminpass"
    }, headers={"X-Bootstrap-Token": "test-bootstrap-token"})
    if response.status_code != 200:
        print(f"Bootstrap failed: {response.status_code} - {response.json()}")
        print(f"Settings token: {settings.admin_bootstrap_token}")
    assert response.status_code == 200

    session_cookie = response.cookies[settings.session_cookie_name]
    client.cookies.set(settings.session_cookie_name, session_cookie)
    return client


def test_providers_requires_auth(client):
    """Test that /providers requires authentication."""
    response = client.get("/providers")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


def test_providers_returns_provider_list(authenticated_client):
    """Test /providers returns list of providers."""
    response = authenticated_client.get("/providers")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2  # lmstudio and ollama

    provider_ids = [p["provider_id"] for p in data]
    assert "lmstudio" in provider_ids
    assert "ollama" in provider_ids

    for provider in data:
        assert "provider_id" in provider
        assert "name" in provider
        assert "capabilities" in provider
        assert "models" in provider
        assert provider["models"] == []  # include_models=false by default


def test_providers_with_models_requires_auth(client):
    """Test that /providers?include_models=true requires authentication."""
    response = client.get("/providers?include_models=true")
    assert response.status_code == 401


def test_providers_with_models_returns_models(authenticated_client, monkeypatch):
    """Test /providers?include_models=true returns models (may timeout gracefully)."""
    response = authenticated_client.get("/providers?include_models=true")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

    for provider in data:
        assert "models" in provider
        # Models may be empty if providers are unreachable (expected in tests)


def test_provider_models_requires_auth(client):
    """Test that /providers/{id}/models requires authentication."""
    response = client.get("/providers/lmstudio/models")
    assert response.status_code == 401


def test_provider_models_returns_models(authenticated_client):
    """Test /providers/{id}/models returns models."""
    response = authenticated_client.get("/providers/lmstudio/models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    # May be empty if unreachable


def test_provider_health_requires_auth(client):
    """Test that /providers/{id}/health requires authentication."""
    response = client.get("/providers/lmstudio/health")
    assert response.status_code == 401


def test_provider_health_returns_health(authenticated_client):
    """Test /providers/{id}/health returns health status."""
    response = authenticated_client.get("/providers/lmstudio/health")
    assert response.status_code == 200
    data = response.json()
    assert "ok" in data
    assert "detail" in data
    # ok may be False if unreachable


def test_unknown_provider_returns_error(authenticated_client):
    """Test unknown provider returns PROVIDER_ERROR."""
    response = authenticated_client.get("/providers/unknown/models")
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "PROVIDER_ERROR"
    assert "Unknown provider" in data["message"]


# Mock transport tests for error handling
def test_provider_unreachable_error(monkeypatch, authenticated_client):
    """Test PROVIDER_UNREACHABLE error when ConnectError occurs."""
    # Mock httpx.AsyncClient to raise ConnectError
    original_init = httpx.AsyncClient.__init__

    def mock_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        # Replace transport with one that raises ConnectError
        self._transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError("Connection failed")))

    monkeypatch.setattr(httpx.AsyncClient, "__init__", mock_init)

    # Rebuild registry with mocked client
    from backend.app.providers.registry import registry
    registry._providers.clear()
    registry.build_registry()

    response = authenticated_client.get("/providers/lmstudio/health")
    assert response.status_code == 503
    data = response.json()
    assert data["code"] == "PROVIDER_UNREACHABLE"
    assert "request_id" in data


# Test with mocked OpenAI-compatible responses
def test_openai_compat_provider_with_mock(monkeypatch, authenticated_client):
    """Test OpenAI-compatible provider with mocked responses."""

    # Mock responses for list_models and healthcheck
    def mock_get(request):
        if "/models" in str(request.url):
            return httpx.Response(200, json={"data": [{"id": "gpt-4"}, {"id": "gpt-3.5-turbo"}]})
        return httpx.Response(404)

    def mock_post(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "Hello"}}]})

    # Create a registry with mocked OpenAI provider
    from backend.app.providers.registry import ProviderRegistry
    from backend.app.providers.openai_compat import OpenAICompatProvider

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_get if mock_get else mock_post))

    test_registry = ProviderRegistry()
    test_registry._providers["test_openai"] = OpenAICompatProvider(
        provider_id="test_openai",
        display_name="Test OpenAI",
        base_url="http://mock.example.com",
        api_key="test-key",
        client=mock_client,
    )

    # Monkeypatch the global registry temporarily
    original_registry = authenticated_client.app.state.registry if hasattr(authenticated_client.app.state, 'registry') else None
    monkeypatch.setattr("backend.app.api.providers.registry", test_registry)

    try:
        response = authenticated_client.get("/providers/test_openai/models")
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert len(data["models"]) == 2
        assert data["models"][0]["id"] == "gpt-4"
    finally:
        # Restore if needed
        if original_registry:
            monkeypatch.setattr("backend.app.api.providers.registry", original_registry)