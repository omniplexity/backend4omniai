from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.auth.password import hash_password
from backend.auth.session import create_session, validate_session
from backend.config import get_settings
from backend.db import Base, dispose_engine
from backend.db.database import get_engine
from backend.db.models import Conversation, MemoryEntry, User
from backend.main import create_app


def _setup_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "privacy.db"
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


def test_export_excludes_secrets_and_delete_removes_user(monkeypatch, tmp_path):
    engine = _setup_db(tmp_path, monkeypatch)
    settings = get_settings()

    db = _get_session(engine)
    try:
        pw = "password123"
        user = User(
            email="u@example.com",
            username="u1",
            hashed_password=hash_password(pw),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        convo = Conversation(user_id=user.id, title="t")
        db.add(convo)
        db.add(MemoryEntry(user_id=user.id, title="Fact", content="Remember this"))
        db.commit()

        session_token, csrf = create_session(db, user)
        user_id = user.id
    finally:
        db.close()

    app = create_app()
    with TestClient(app) as client:
        client.cookies.set(settings.session_cookie_name, session_token)
        client.cookies.set(settings.csrf_cookie_name, csrf)

        exp = client.get("/api/auth/export")
        assert exp.status_code == 200
        body = exp.json()
        assert body["user"]["id"] == user_id
        assert "hashed_password" not in body["user"]
        assert isinstance(body["conversations"], list)
        assert isinstance(body["memory"], list)

        # Delete is CSRF-protected (middleware), so include header.
        deleted = client.post(
            "/api/auth/delete",
            json={"password": "password123"},
            headers={settings.csrf_header_name: csrf},
        )
        assert deleted.status_code == 200

    db = _get_session(engine)
    try:
        assert db.query(User).filter(User.id == user_id).first() is None
        assert validate_session(db, session_token) is None
    finally:
        db.close()
        dispose_engine()

