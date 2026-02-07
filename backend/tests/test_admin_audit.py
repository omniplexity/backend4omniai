from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.auth.dependencies import get_admin_user
from backend.config import get_settings
from backend.db import Base, dispose_engine
from backend.db.database import get_engine
from backend.db.models import User
from backend.main import create_app


def _setup_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "admin_audit.db"
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


def test_admin_actions_write_audit_and_audit_endpoint_returns_entries(monkeypatch, tmp_path):
    engine = _setup_db(tmp_path, monkeypatch)
    db = _get_session(engine)
    try:
        admin = User(
            email="admin@example.com",
            username="admin",
            hashed_password="x",
            is_active=True,
            is_admin=True,
        )
        user = User(
            email="u@example.com",
            username="u1",
            hashed_password="x",
            is_active=True,
            is_admin=False,
        )
        db.add(admin)
        db.add(user)
        db.commit()
        db.refresh(admin)
        db.refresh(user)
        admin_id = admin.id
        user_id = user.id
    finally:
        db.close()

    app = create_app()

    async def _override_admin():
        db2 = _get_session(engine)
        try:
            return db2.query(User).filter(User.id == admin_id).first()
        finally:
            db2.close()

    app.dependency_overrides[get_admin_user] = _override_admin

    with TestClient(app) as client:
        res = client.patch(f"/api/admin/users/{user_id}", json={"is_active": False})
        assert res.status_code == 200

        res = client.get("/api/admin/audit")
        assert res.status_code == 200
        body = res.json()
        assert isinstance(body.get("entries"), list)
        assert any(e["event_type"] == "admin.user_update" for e in body["entries"])

    dispose_engine()

