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
    db_path = tmp_path / "memory_semantic.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("DATABASE_URL_POSTGRES", "")
    monkeypatch.setenv("EMBEDDINGS_ENABLED", "true")
    monkeypatch.setenv("EMBEDDINGS_MODEL", "dummy-embed")
    monkeypatch.setenv("EMBEDDINGS_PROVIDER_PREFERENCE", "ollama")
    get_settings.cache_clear()
    dispose_engine()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    return engine


def _get_session(engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


class _Caps:
    embeddings = True


class _DummyEmbedProvider:
    async def capabilities(self, model=None):
        return _Caps()

    async def embed_texts(self, texts, model=None):
        # Very simple 2D embedding:
        # - texts containing "cat" -> [1, 0]
        # - everything else -> [0, 1]
        out = []
        for t in texts:
            if "cat" in (t or "").lower():
                out.append([1.0, 0.0])
            else:
                out.append([0.0, 1.0])
        return out


class _DummyRegistry:
    def __init__(self):
        self.providers = {"ollama": _DummyEmbedProvider()}


def test_memory_semantic_search_prefers_embeddings(monkeypatch, tmp_path):
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
    app.state.provider_registry = _DummyRegistry()

    async def override_get_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as client:
        a = client.post("/api/memory", json={"title": "Cats", "content": "cat facts"})
        b = client.post("/api/memory", json={"title": "Dogs", "content": "dog facts"})
        assert a.status_code == 201
        assert b.status_code == 201

        res = client.post("/api/memory/search", json={"query": "cat", "limit": 5})
        assert res.status_code == 200
        items = res.json()
        assert len(items) >= 1
        assert items[0]["title"] == "Cats"
        assert items[0]["score"] >= items[-1]["score"]

    dispose_engine()

