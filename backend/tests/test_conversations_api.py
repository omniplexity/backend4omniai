import pytest

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
    assert response.status_code == 200

    session_cookie = response.cookies[settings.session_cookie_name]
    csrf_token = response.json()["csrf_token"]

    client.cookies.set(settings.session_cookie_name, session_cookie)
    client.csrf_token = csrf_token  # Store for use in tests

    return client


@pytest.fixture
def regular_user_client(client, db_session):
    """Test client with authenticated regular user."""
    from backend.app.db.models import User
    from backend.app.auth.password import hash_password

    # Create a regular user
    db = db_session
    regular_user = User(
        username="regular",
        password_hash=hash_password("pass"),
        role="user",
        status="active"
    )
    db.add(regular_user)
    db.commit()

    # Login as regular user
    response = client.post("/auth/login", json={"username": "regular", "password": "pass"})
    assert response.status_code == 200
    session_cookie = response.cookies[settings.session_cookie_name]
    csrf_token = response.json()["csrf_token"]

    # Create a new client instance to avoid cookie conflicts
    from fastapi.testclient import TestClient
    from backend.app.main import app
    regular_client = TestClient(app)
    regular_client.cookies.set(settings.session_cookie_name, session_cookie)
    regular_client.csrf_token = csrf_token

    return regular_client


def test_get_conversation_by_id_owner_access(authenticated_client):
    """Test that conversation owner can fetch their conversation by ID."""
    # Create conversation
    response = authenticated_client.post(
        "/conversations",
        json={"title": "Test Conversation"},
        headers={"X-CSRF-Token": authenticated_client.csrf_token}
    )
    assert response.status_code == 200
    conv_id = response.json()["id"]

    # Get conversation by ID
    response = authenticated_client.get(f"/conversations/{conv_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == conv_id
    assert data["title"] == "Test Conversation"
    assert "created_at" in data
    assert "updated_at" in data


def test_get_conversation_by_id_non_owner_access(regular_user_client, authenticated_client):
    """Test that non-owner cannot fetch another user's conversation by ID."""
    # Create conversation as admin
    response = authenticated_client.post(
        "/conversations",
        json={"title": "Admin Conversation"},
        headers={"X-CSRF-Token": authenticated_client.csrf_token}
    )
    assert response.status_code == 200
    admin_conv_id = response.json()["id"]

    # Try to access as regular user - should get 404 (existing convention)
    response = regular_user_client.get(f"/conversations/{admin_conv_id}")
    assert response.status_code == 404
    assert response.json()["code"] == "CONVERSATION_NOT_FOUND"


def test_get_conversation_by_id_nonexistent(authenticated_client):
    """Test that accessing nonexistent conversation returns 404."""
    response = authenticated_client.get("/conversations/99999")
    assert response.status_code == 404
    assert response.json()["code"] == "CONVERSATION_NOT_FOUND"


def test_get_conversation_requires_auth(client):
    """Test that GET /conversations/{id} requires authentication."""
    response = client.get("/conversations/1")
    assert response.status_code == 401


def test_request_body_enforced_for_post_conversations(client):
    """Test that POST /conversations enforces JSON request body."""
    # Bootstrap admin first
    client.post("/admin/bootstrap", json={
        "username": "admin",
        "password": "adminpass"
    }, headers={"X-Bootstrap-Token": "test-bootstrap-token"})

    login_response = client.post("/auth/login", json={
        "username": "admin",
        "password": "adminpass"
    })
    session_cookie = login_response.cookies[settings.session_cookie_name]
    csrf_token = login_response.json()["csrf_token"]
    client.cookies.set(settings.session_cookie_name, session_cookie)

    # Try without body - should fail with 400 (malformed request)
    response = client.post("/conversations", headers={"X-CSRF-Token": csrf_token})
    assert response.status_code == 400  # Bad request for missing body

    # With valid body should work
    response = client.post(
        "/conversations",
        json={"title": "Test"},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 200


def test_request_body_enforced_for_patch_conversations(authenticated_client):
    """Test that PATCH /conversations/{id} enforces JSON request body."""
    # Create conversation
    response = authenticated_client.post(
        "/conversations",
        json={"title": "Test"},
        headers={"X-CSRF-Token": authenticated_client.csrf_token}
    )
    conv_id = response.json()["id"]

    # Try without body - should fail
    response = authenticated_client.patch(
        f"/conversations/{conv_id}",
        headers={"X-CSRF-Token": authenticated_client.csrf_token}
    )
    assert response.status_code == 400  # Bad request for missing body

    # With valid body should work
    response = authenticated_client.patch(
        f"/conversations/{conv_id}",
        json={"title": "New Title"},
        headers={"X-CSRF-Token": authenticated_client.csrf_token}
    )
    assert response.status_code == 200


def test_request_body_enforced_for_post_messages(authenticated_client):
    """Test that POST /conversations/{id}/messages enforces JSON request body."""
    # Create conversation
    response = authenticated_client.post(
        "/conversations",
        json={"title": "Test"},
        headers={"X-CSRF-Token": authenticated_client.csrf_token}
    )
    conv_id = response.json()["id"]

    # Try without body - should fail
    response = authenticated_client.post(
        f"/conversations/{conv_id}/messages",
        headers={"X-CSRF-Token": authenticated_client.csrf_token}
    )
    assert response.status_code == 400  # Bad request for missing body

    # With valid body should work
    response = authenticated_client.post(
        f"/conversations/{conv_id}/messages",
        json={"content": "Test message"},
        headers={"X-CSRF-Token": authenticated_client.csrf_token}
    )
    assert response.status_code == 200


def test_request_body_enforced_for_post_stream(authenticated_client):
    """Test that POST /conversations/{id}/stream enforces JSON request body."""
    # Create conversation
    response = authenticated_client.post(
        "/conversations",
        json={"title": "Test"},
        headers={"X-CSRF-Token": authenticated_client.csrf_token}
    )
    conv_id = response.json()["id"]

    # Add a message first
    authenticated_client.post(
        f"/conversations/{conv_id}/messages",
        json={"content": "Test message"},
        headers={"X-CSRF-Token": authenticated_client.csrf_token}
    )

    # Try without body - should fail
    response = authenticated_client.post(
        f"/conversations/{conv_id}/stream",
        headers={"X-CSRF-Token": authenticated_client.csrf_token}
    )
    assert response.status_code == 400  # Bad request for missing body


def test_request_body_enforced_for_post_retry(authenticated_client):
    """Test that POST /chat/retry enforces JSON request body."""
    # Create conversation with messages
    response = authenticated_client.post(
        "/conversations",
        json={"title": "Test"},
        headers={"X-CSRF-Token": authenticated_client.csrf_token}
    )
    conv_id = response.json()["id"]

    authenticated_client.post(
        f"/conversations/{conv_id}/messages",
        json={"content": "Test message"},
        headers={"X-CSRF-Token": authenticated_client.csrf_token}
    )

    # Try without body - should fail
    response = authenticated_client.post(
        "/chat/retry",
        headers={"X-CSRF-Token": authenticated_client.csrf_token}
    )
    assert response.status_code == 400  # Bad request for missing body

    # With valid body should work
    response = authenticated_client.post(
        "/chat/retry",
        json={
            "conversation_id": conv_id,
            "provider_id": "lmstudio",
            "model": "fake-model"
        },
        headers={"X-CSRF-Token": authenticated_client.csrf_token}
    )
    assert response.status_code == 200