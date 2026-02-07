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
    db_path = tmp_path / "knowledge_api.db"
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


def test_knowledge_upload_and_search(monkeypatch, tmp_path):
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
        upload = client.post(
            "/api/knowledge/upload",
            files={"file": ("doc.txt", b"hello world from omniai knowledge", "text/plain")},
        )
        assert upload.status_code == 201
        doc = upload.json()
        assert doc["name"] == "doc.txt"
        assert doc["chunks"] >= 1

        listed = client.get("/api/knowledge")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        search = client.post("/api/knowledge/search", json={"query": "omniai", "limit": 3})
        assert search.status_code == 200
        results = search.json()
        assert len(results) >= 1
        assert results[0]["doc_name"] == "doc.txt"

    dispose_engine()
