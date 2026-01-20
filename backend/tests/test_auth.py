import pytest
from datetime import datetime, timedelta, timezone

from backend.app.main import app
from backend.app.db.repo.invites_repo import create_invite
from backend.app.config.settings import settings


def test_register_requires_valid_invite(client):
    """Test that registration requires a valid invite."""
    response = client.post("/auth/register", json={
        "invite_code": "invalid",
        "username": "testuser",
        "password": "testpass"
    })
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_INVITE"


def test_register_consumes_invite_and_creates_user_and_session_cookie(client, db_session):
    """Test successful registration with valid invite."""
    # Create a valid invite in the DB
    invite = create_invite(
        db_session,
        code="valid-invite-code",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        created_by=None
    )
    db_session.commit()

    # Register
    response = client.post("/auth/register", json={
        "invite_code": "valid-invite-code",
        "username": "testuser",
        "password": "testpass"
    })
    assert response.status_code == 200
    data = response.json()
    assert "user" in data
    assert data["user"]["username"] == "testuser"
    assert "csrf_token" in data

    # Check cookie is set
    assert settings.session_cookie_name in response.cookies
    session_cookie = response.cookies[settings.session_cookie_name]
    assert session_cookie is not None

    # Verify invite is consumed
    from backend.app.db.models import Invite
    invite = db_session.query(Invite).filter(Invite.code == "valid-invite-code").first()
    assert invite.used_by is not None


def test_login_sets_cookie_and_returns_csrf(client):
    """Test login creates session and returns CSRF token."""
    # First bootstrap an admin
    response = client.post("/admin/bootstrap", json={
        "username": "admin",
        "password": "adminpass"
    }, headers={"X-Bootstrap-Token": "test-bootstrap-token"})
    assert response.status_code == 200

    # Login
    response = client.post("/auth/login", json={
        "username": "admin",
        "password": "adminpass"
    })
    assert response.status_code == 200
    data = response.json()
    assert "user" in data
    assert data["user"]["username"] == "admin"
    assert "csrf_token" in data

    # Check cookie
    assert settings.session_cookie_name in response.cookies


def test_logout_requires_csrf(client):
    """Test logout requires CSRF token."""
    # Bootstrap and login
    client.post("/admin/bootstrap", json={
        "username": "admin",
        "password": "adminpass"
    }, headers={"X-Bootstrap-Token": "test-bootstrap-token"})

    login_response = client.post("/auth/login", json={
        "username": "admin",
        "password": "adminpass"
    })
    csrf_token = login_response.json()["csrf_token"]

    # Logout without CSRF should fail
    response = client.post("/auth/logout")
    assert response.status_code == 401  # No session

    # With session but no CSRF
    session_cookie = login_response.cookies[settings.session_cookie_name]
    client.cookies.set(settings.session_cookie_name, session_cookie)
    response = client.post("/auth/logout")
    assert response.status_code == 403  # CSRF invalid

    # With CSRF should succeed
    response = client.post("/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully"


def test_admin_invite_create_requires_admin_and_csrf(client):
    """Test invite creation requires admin and CSRF."""
    # Bootstrap admin
    bootstrap_response = client.post("/admin/bootstrap", json={
        "username": "admin",
        "password": "adminpass"
    }, headers={"X-Bootstrap-Token": "test-bootstrap-token"})
    csrf_token = bootstrap_response.json()["csrf_token"]
    session_cookie = bootstrap_response.cookies[settings.session_cookie_name]

    # Set session cookie
    client.cookies.set(settings.session_cookie_name, session_cookie)

    # Create invite without CSRF should fail
    response = client.post("/admin/invites", json={"expires_in_hours": 24})
    assert response.status_code == 403  # CSRF invalid

    # With CSRF should succeed
    response = client.post("/admin/invites", json={"expires_in_hours": 24}, headers={"X-CSRF-Token": csrf_token})
    assert response.status_code == 200
    data = response.json()
    assert "invite_code" in data
    assert "expires_at" in data


def test_me_requires_session(client):
    """Test /me endpoint requires valid session."""
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


def test_login_then_me_succeeds(client):
    """Test login creates session and /me works with cookie."""
    # Bootstrap admin
    client.post("/admin/bootstrap", json={
        "username": "admin",
        "password": "adminpass"
    }, headers={"X-Bootstrap-Token": "test-bootstrap-token"})

    # Login
    login_response = client.post("/auth/login", json={
        "username": "admin",
        "password": "adminpass"
    })
    assert login_response.status_code == 200

    # Check cookie is set
    assert settings.session_cookie_name in login_response.cookies
    session_cookie = login_response.cookies[settings.session_cookie_name]

    # /me should work with cookie
    client.cookies.set(settings.session_cookie_name, session_cookie)
    me_response = client.get("/auth/me")
    assert me_response.status_code == 200
    data = me_response.json()
    assert data["user"]["username"] == "admin"
    assert data["user"]["role"] == "admin"


def test_bootstrap_sets_cookie(client):
    """Test bootstrap creates admin user and sets session cookie."""
    response = client.post("/admin/bootstrap", json={
        "username": "admin",
        "password": "adminpass"
    }, headers={"X-Bootstrap-Token": "test-bootstrap-token"})
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["username"] == "admin"
    assert data["user"]["role"] == "admin"
    assert "csrf_token" in data

    # Check cookie is set
    assert settings.session_cookie_name in response.cookies
    session_cookie = response.cookies[settings.session_cookie_name]
    assert session_cookie is not None

    # /me should work with the cookie
    client.cookies.set(settings.session_cookie_name, session_cookie)
    me_response = client.get("/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["user"]["username"] == "admin"


def test_bootstrap_creates_audit_log(client, db_session):
    """Test bootstrap creates an audit log entry."""
    response = client.post("/admin/bootstrap", json={
        "username": "admin",
        "password": "adminpass"
    }, headers={"X-Bootstrap-Token": "test-bootstrap-token"})
    assert response.status_code == 200

    # Check audit log
    from backend.app.db.models import AuditLog
    audit_logs = db_session.query(AuditLog).all()
    assert len(audit_logs) == 1
    log = audit_logs[0]
    assert log.action == "ADMIN_BOOTSTRAP"
    assert log.target.startswith("user:")
    assert log.actor_user_id is not None


def test_preflight_cors_allowed_without_origin_lock(client):
    """Regression test: OPTIONS requests return 200 with CORS headers even without origin lock."""
    response = client.options("/auth/me", headers={
        "Origin": "https://omniplexity.github.io",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "X-CSRF-Token, Content-Type"
    })
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://omniplexity.github.io"
    assert response.headers.get("access-control-allow-credentials") == "true"
    allow_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "x-csrf-token" in allow_headers
    assert "content-type" in allow_headers


def test_origin_lock_blocks_without_secret(client, monkeypatch):
    """Regression test: GET /health allowed without origin lock secret (for monitoring)."""
    # Enable origin lock and test environment
    monkeypatch.setattr(settings, "origin_lock_enabled", True)
    monkeypatch.setattr(settings, "origin_lock_secret", "test-secret")
    monkeypatch.setattr(settings, "environment", "test")

    # /health is allowed for monitoring even without secret
    response = client.get("/health", headers={"X-Test-Client-IP": "8.8.8.8"})
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}