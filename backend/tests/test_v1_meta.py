from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.auth.session import create_session
from backend.config import get_settings
from backend.db import Base, dispose_engine
from backend.db.database import get_engine
from backend.db.models import User
from backend.main import create_app


def _setup_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "v1_meta.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("DATABASE_URL_POSTGRES", "")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_ENABLED", "false")
    get_settings.cache_clear()
    dispose_engine()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    return engine


def _get_session(engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


class _DummyRegistry:
    providers: dict = {}


SERVER_BACKED_FEATURES = [
    "chat_sse_v2",
    "voice",
    "vision",
    "tools",
    "connectors",
    "mcp",
    "media_generation",
    "knowledge_rag",
    "citations",
    "chat_projects",
    "chat_context_manager",
    "chat_branches",
    "chat_canvas",
    "chat_artifacts",
    "chat_run_inspector",
]


def test_v1_meta_unauthenticated(monkeypatch, tmp_path):
    _setup_db(tmp_path, monkeypatch)
    settings = get_settings()

    app = create_app()
    # Avoid initializing real provider backends during this test.
    app.state.provider_registry = _DummyRegistry()

    with TestClient(app) as client:
        res = client.get("/v1/meta")
        assert res.status_code == 200
        body = res.json()

        assert body["meta_version"] == 1
        assert "server" in body
        assert "auth" in body
        assert "capabilities" in body
        assert "features" in body

        assert body["auth"]["authenticated"] is False
        assert body["auth"]["user"] is None
        assert body["auth"]["session_cookie_name"] == settings.session_cookie_name
        assert body["auth"]["csrf"]["cookie_name"] == settings.csrf_cookie_name
        assert body["auth"]["csrf"]["header_name"] == settings.csrf_header_name

        for feature_id in SERVER_BACKED_FEATURES:
            assert feature_id in body["features"]
            assert body["features"][feature_id]["permitted"] is False

        assert body["features"]["tools"]["supported"] is True
        assert body["features"]["tools"]["reason"] == "login_required"
        assert body["features"]["citations"]["supported"] is False
        assert body["features"]["citations"]["reason"] == "not_supported"

    dispose_engine()


def test_v1_meta_authenticated(monkeypatch, tmp_path):
    engine = _setup_db(tmp_path, monkeypatch)
    settings = get_settings()

    db = _get_session(engine)
    try:
        user = User(email="meta@example.com", username="metauser", hashed_password="hashed", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        session_token, _csrf_token = create_session(db, user)
    finally:
        db.close()

    app = create_app()
    app.state.provider_registry = _DummyRegistry()

    with TestClient(app) as client:
        client.cookies.set(settings.session_cookie_name, session_token)

        res = client.get("/v1/meta")
        assert res.status_code == 200
        body = res.json()

        assert body["auth"]["authenticated"] is True
        assert body["auth"]["user"]["username"] == "metauser"
        assert body["auth"]["user"]["email"] == "meta@example.com"

        # Auth-gated feature becomes permitted when authenticated.
        assert body["features"]["tools"]["supported"] is True
        assert body["features"]["tools"]["permitted"] is True
        assert body["features"]["tools"]["reason"] == "ok"

    dispose_engine()

