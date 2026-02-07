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
    db_path = tmp_path / "csrf_refresh.db"
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


def test_get_csrf_requires_session(monkeypatch, tmp_path):
    _setup_db(tmp_path, monkeypatch)
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/api/auth/csrf")
        assert res.status_code == 401


def test_get_csrf_returns_token_and_sets_cookie(monkeypatch, tmp_path):
    engine = _setup_db(tmp_path, monkeypatch)
    settings = get_settings()

    db = _get_session(engine)
    try:
        user = User(email="csrf@example.com", username="csrf", hashed_password="hashed", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        session_token, csrf_token = create_session(db, user)
    finally:
        db.close()

    app = create_app()

    with TestClient(app) as client:
        client.cookies.set(settings.session_cookie_name, session_token)
        res = client.get("/api/auth/csrf")
        assert res.status_code == 200
        body = res.json()
        assert body["csrf_token"] == csrf_token
        set_cookie = res.headers.get("set-cookie", "")
        assert f"{settings.csrf_cookie_name}=" in set_cookie

    dispose_engine()

