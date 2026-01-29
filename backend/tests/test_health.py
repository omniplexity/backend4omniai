"""
Tests for health check endpoints.
"""

from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_healthz_returns_200(self, client: TestClient):
        """Health check should return 200 OK."""
        response = client.get("/healthz")
        assert response.status_code == 200

    def test_healthz_returns_ok_status(self, client: TestClient):
        """Health check should return ok status."""
        response = client.get("/healthz")
        data = response.json()
        assert data["status"] == "ok"

    def test_healthz_contains_required_fields(self, client: TestClient):
        """Health check should contain all required fields."""
        response = client.get("/healthz")
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data

    def test_healthz_has_request_id_header(self, client: TestClient):
        """Health check response should include X-Request-ID header."""
        response = client.get("/healthz")
        assert "X-Request-ID" in response.headers

    def test_readyz_returns_200(self, client: TestClient):
        """Readiness check should return 200 OK."""
        response = client.get("/readyz")
        assert response.status_code == 200

    def test_readyz_returns_ready_status(self, client: TestClient):
        """Readiness check should return ready status."""
        response = client.get("/readyz")
        data = response.json()
        assert data["status"] == "ready"

    def test_readyz_contains_checks(self, client: TestClient):
        """Readiness check should contain dependency checks."""
        response = client.get("/readyz")
        data = response.json()
        assert "checks" in data
        assert isinstance(data["checks"], dict)


class TestCORS:
    """Test CORS configuration."""

    def test_cors_allows_configured_origin(self, client: TestClient):
        """CORS should allow configured origin."""
        response = client.options(
            "/healthz",
            headers={
                "Origin": "https://omniplexity.github.io",
                "Access-Control-Request-Method": "GET",
            },
        )
        # OPTIONS returns 200 for allowed origins
        assert response.status_code == 200
        assert (
            response.headers.get("access-control-allow-origin")
            == "https://omniplexity.github.io"
        )

    def test_cors_blocks_unknown_origin(self, client: TestClient):
        """CORS should not include allow header for unknown origins."""
        response = client.options(
            "/healthz",
            headers={
                "Origin": "https://malicious-site.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # No access-control-allow-origin for blocked origins
        assert "access-control-allow-origin" not in response.headers


class TestRequestContext:
    """Test request context middleware."""

    def test_custom_request_id_preserved(self, client: TestClient):
        """Custom request ID should be preserved in response."""
        custom_id = "test-request-123"
        response = client.get("/healthz", headers={"X-Request-ID": custom_id})
        assert response.headers.get("X-Request-ID") == custom_id

    def test_request_id_generated_if_missing(self, client: TestClient):
        """Request ID should be generated if not provided."""
        response = client.get("/healthz")
        request_id = response.headers.get("X-Request-ID")
        assert request_id is not None
        assert len(request_id) > 0
