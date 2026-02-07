from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.auth.dependencies import get_current_user
from backend.config import get_settings
from backend.db import Base, dispose_engine
from backend.db.database import get_engine
from backend.db.models import MemoryEntry, User
from backend.main import create_app
from backend.providers.base import ChatResponse, ProviderCapabilities


def _setup_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "chat_rag.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("DATABASE_URL_POSTGRES", "")
    monkeypatch.setenv("EMBEDDINGS_ENABLED", "false")
    get_settings.cache_clear()
    dispose_engine()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    return engine


def _get_session(engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


class _DummyProvider:
    async def healthcheck(self) -> bool:
        return True

    async def list_models(self):
        return []

    async def capabilities(self, model=None):
        return ProviderCapabilities(streaming=False, embeddings=False)

    async def chat_once(self, request):
        # Assert RAG context message was injected.
        sys_msgs = [m.content for m in request.messages if m.role == "system"]
        assert any("Context sources" in (s or "") for s in sys_msgs)
        # Respond with a citation label.
        return ChatResponse(content="Use memory fact. [S1]", model=request.model, finish_reason="stop")

    async def chat_stream(self, request):
        raise NotImplementedError()


class _DummyRegistry:
    def __init__(self):
        self.default_provider = "dummy"
        self.providers = {"dummy": _DummyProvider()}

    def get_provider(self, name=None):
        return self.providers.get(name or self.default_provider)


def test_chat_completion_persists_citations(monkeypatch, tmp_path):
    engine = _setup_db(tmp_path, monkeypatch)
    db = _get_session(engine)
    try:
        user = User(email="u@example.com", username="u1", hashed_password="x", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        mem = MemoryEntry(user_id=user.id, title="Fact", content="Remember cats")
        db.add(mem)
        db.commit()
    finally:
        db.close()

    app = create_app()
    app.state.provider_registry = _DummyRegistry()

    async def override_get_current_user():
        db2 = _get_session(engine)
        try:
            return db2.query(User).filter(User.id == user_id).first()
        finally:
            db2.close()

    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as client:
        # Create conversation
        convo = client.post("/api/chat/conversations", json={"title": "t"}).json()
        convo_id = convo["id"]
        res = client.post(
            f"/api/chat/conversations/{convo_id}/messages",
            json={"content": "cats", "stream": False, "provider": "dummy"},
        )
        assert res.status_code == 200

        msgs = client.get(f"/api/chat/conversations/{convo_id}/messages").json()
        assistant = [m for m in msgs if m["role"] == "assistant"][-1]
        assert assistant["citations_json"] is not None
        assert "sources" in assistant["citations_json"]
        assert assistant["citations_json"]["used_labels"] == ["S1"]

    dispose_engine()
