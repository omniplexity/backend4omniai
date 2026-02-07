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
    db_path = tmp_path / "sessions_api.db"
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


def test_list_and_revoke_sessions(monkeypatch, tmp_path):
    engine = _setup_db(tmp_path, monkeypatch)
    settings = get_settings()

    db = _get_session(engine)
    try:
        user = User(email="u@example.com", username="u1", hashed_password="x", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        tok1, csrf1 = create_session(db, user)
        tok2, _csrf2 = create_session(db, user)
    finally:
        db.close()

    app = create_app()
    with TestClient(app) as client:
        client.cookies.set(settings.session_cookie_name, tok1)
        client.cookies.set(settings.csrf_cookie_name, csrf1)

        res = client.get("/api/auth/sessions")
        assert res.status_code == 200
        sessions = res.json()
        assert len(sessions) == 2
        current = [s for s in sessions if s["is_current"]]
        assert len(current) == 1

        # Revoke the non-current session (pick first where is_current=False)
        target = [s for s in sessions if not s["is_current"]][0]
        del_res = client.delete(
            f"/api/auth/sessions/{target['id']}",
            headers={settings.csrf_header_name: csrf1},
        )
        assert del_res.status_code == 200

        res2 = client.get("/api/auth/sessions")
        assert res2.status_code == 200
        assert len(res2.json()) == 1

        # Revoke all except current should delete 0 now.
        res3 = client.post(
            "/api/auth/sessions/revoke_all",
            headers={settings.csrf_header_name: csrf1},
        )
        assert res3.status_code == 200
        assert res3.json()["deleted"] == 0

    dispose_engine()

