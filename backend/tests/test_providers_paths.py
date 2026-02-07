from fastapi.testclient import TestClient

from backend.auth.dependencies import get_current_user
from backend.main import create_app


def test_providers_paths_do_not_redirect_and_include_cors_headers():
    app = create_app()

    async def override_get_current_user():
        return object()

    app.dependency_overrides[get_current_user] = override_get_current_user

    origin = "https://omniplexity.github.io"
    headers = {"Origin": origin}

    with TestClient(app) as client:
        res = client.get("/api/providers", headers=headers, follow_redirects=False)
        assert res.status_code not in (307, 308)
        assert res.headers.get("location") is None
        assert res.headers.get("access-control-allow-origin") == origin

        res2 = client.get("/api/providers/", headers=headers, follow_redirects=False)
        assert res2.status_code not in (307, 308)
        assert res2.headers.get("location") is None
        assert res2.headers.get("access-control-allow-origin") == origin

