from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.auth.dependencies import get_current_user
from backend.config import get_settings
from backend.db import Base, dispose_engine
from backend.db.database import get_engine
from backend.db.models import User
from backend.main import create_app


def _setup_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "memory_api.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("DATABASE_URL_POSTGRES", "")
    get_settings.cache_clear()
    dispose_engine()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    return engine


def _get_session(engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def test_memory_crud(monkeypatch, tmp_path):
    engine = _setup_db(tmp_path, monkeypatch)
    db = _get_session(engine)
    try:
        user = User(email="user@example.com", username="user", hashed_password="hashed", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
    finally:
        db.close()

    app = create_app()

    async def override_get_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as client:
        created = client.post("/api/memory", json={"title": "Fact", "content": "Remember this", "tags": ["core"]})
        assert created.status_code == 201
        body = created.json()
        assert body["title"] == "Fact"

        listed = client.get("/api/memory")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        updated = client.patch(f"/api/memory/{body['id']}", json={"content": "Updated"})
        assert updated.status_code == 200
        assert updated.json()["content"] == "Updated"

        deleted = client.delete(f"/api/memory/{body['id']}")
        assert deleted.status_code == 200
        assert deleted.json()["message"] == "Memory entry deleted"

        listed2 = client.get("/api/memory")
        assert listed2.status_code == 200
        assert listed2.json() == []

    dispose_engine()
