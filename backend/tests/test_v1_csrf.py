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
    db_path = tmp_path / "v1_csrf.db"
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


def test_v1_conversations_require_csrf(monkeypatch, tmp_path):
    engine = _setup_db(tmp_path, monkeypatch)
    settings = get_settings()

    db = _get_session(engine)
    try:
        user = User(email="v1@example.com", username="v1user", hashed_password="hashed", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        session_token, csrf_token = create_session(db, user)
    finally:
        db.close()

    app = create_app()
    with TestClient(app) as client:
        client.cookies.set(settings.session_cookie_name, session_token)
        client.cookies.set(settings.csrf_cookie_name, csrf_token)

        res = client.post("/v1/conversations", json={"title": "Test"})
        assert res.status_code == 403
        body = res.json()
        assert body["error"]["code"] == "E2002"

        res = client.post(
            "/v1/conversations",
            json={"title": "Test"},
            headers={settings.csrf_header_name: csrf_token},
        )
        assert res.status_code == 200

    dispose_engine()
