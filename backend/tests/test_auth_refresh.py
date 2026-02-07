from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.auth.session import create_session, validate_session
from backend.config import get_settings
from backend.db import Base, dispose_engine
from backend.db.database import get_engine
from backend.db.models import User
from backend.main import create_app


def _setup_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "auth_refresh.db"
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


def test_refresh_rotates_session_and_csrf(monkeypatch, tmp_path):
    engine = _setup_db(tmp_path, monkeypatch)
    settings = get_settings()

    db = _get_session(engine)
    try:
        user = User(email="r@example.com", username="r1", hashed_password="x", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        old_session_token, old_csrf = create_session(db, user)
    finally:
        db.close()

    app = create_app()
    new_session_token = None
    with TestClient(app) as client:
        # CSRF middleware requires both cookie + header match.
        client.cookies.set(settings.session_cookie_name, old_session_token)
        client.cookies.set(settings.csrf_cookie_name, old_csrf)
        res = client.post("/api/auth/refresh", headers={settings.csrf_header_name: old_csrf})
        assert res.status_code == 200
        body = res.json()
        assert body["csrf_token"] != old_csrf

        # Pick the rotated cookie value (different from old).
        candidates = [c.value for c in client.cookies.jar if c.name == settings.session_cookie_name]
        assert old_session_token in candidates
        rotated = [v for v in candidates if v != old_session_token]
        assert rotated, f"expected rotated session cookie, got {candidates}"
        new_session_token = rotated[-1]

    db = _get_session(engine)
    try:
        assert validate_session(db, old_session_token) is None
        assert new_session_token is not None
        assert validate_session(db, new_session_token) is not None
    finally:
        db.close()
        dispose_engine()
