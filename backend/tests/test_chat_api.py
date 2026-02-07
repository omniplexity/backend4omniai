"""Tests for Chat API endpoints (Phase 5)."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.auth.session import create_session
from backend.config import get_settings
from backend.db import Base, dispose_engine
from backend.db.database import get_engine
from backend.db.models import User, Conversation
from backend.main import create_app


def _setup_db(tmp_path: Path, monkeypatch):
    """Set up a fresh database for testing."""
    db_path = tmp_path / "chat_api.db"
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
    """Get a database session."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def _create_test_user(db):
    """Create a test user."""
    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password="hashed_password",
        is_active=True,
        is_admin=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_mock_provider_registry(app):
    """Create a mock provider registry for testing."""
    class MockProvider:
        async def healthcheck(self):
            return True

        async def list_models(self):
            return []

        async def capabilities(self, model=None):
            from backend.providers.base import ProviderCapabilities
            return ProviderCapabilities()

        async def chat_once(self, request):
            from backend.providers.base import ChatResponse
            return ChatResponse(
                content="Test response",
                model="test-model",
                finish_reason="stop",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15
            )

        async def chat_stream(self, request):
            from backend.providers.base import ChatChunk
            yield ChatChunk(content="Test ", model="test-model")
            yield ChatChunk(content="response", model="test-model", finish_reason="stop")

    class MockRegistry:
        default_provider = "lmstudio"

        def get_provider(self, name=None):
            return MockProvider()

        def list_providers(self):
            return ["lmstudio"]

    app.state.provider_registry = MockRegistry()


class TestConversationsAPI:
    """Tests for conversation CRUD operations."""

    def test_list_conversations_empty(self, monkeypatch, tmp_path):
        """Test listing conversations when none exist."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            user = _create_test_user(db)
            session_token, csrf_token = create_session(db, user)
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.cookies.set(settings.csrf_cookie_name, csrf_token)
            client.headers[settings.csrf_header_name] = csrf_token

            response = client.get("/api/chat/conversations")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 0

        dispose_engine()

    def test_create_conversation(self, monkeypatch, tmp_path):
        """Test creating a new conversation."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            user = _create_test_user(db)
            session_token, csrf_token = create_session(db, user)
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.cookies.set(settings.csrf_cookie_name, csrf_token)
            client.headers[settings.csrf_header_name] = csrf_token

            response = client.post(
                "/api/chat/conversations",
                json={"title": "Test Conversation", "provider": "lmstudio", "model": "test-model"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "Test Conversation"
            assert data["provider"] == "lmstudio"
            assert data["model"] == "test-model"
            assert "id" in data

        dispose_engine()

    def test_get_conversation(self, monkeypatch, tmp_path):
        """Test getting a specific conversation."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            user = _create_test_user(db)
            session_token, csrf_token = create_session(db, user)

            # Create a conversation
            convo = Conversation(user_id=user.id, title="Test Conversation")
            db.add(convo)
            db.commit()
            db.refresh(convo)
            conversation_id = convo.id
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.headers[settings.csrf_header_name] = csrf_token

            response = client.get(f"/api/chat/conversations/{conversation_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == conversation_id
            assert data["title"] == "Test Conversation"

        dispose_engine()

    def test_get_conversation_not_found(self, monkeypatch, tmp_path):
        """Test getting a non-existent conversation."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            user = _create_test_user(db)
            session_token, csrf_token = create_session(db, user)
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.headers[settings.csrf_header_name] = csrf_token

            response = client.get("/api/chat/conversations/nonexistent-id")
            assert response.status_code == 404

        dispose_engine()

    def test_update_conversation_title(self, monkeypatch, tmp_path):
        """Test updating a conversation title."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            user = _create_test_user(db)
            session_token, csrf_token = create_session(db, user)

            convo = Conversation(user_id=user.id, title="Old Title")
            db.add(convo)
            db.commit()
            db.refresh(convo)
            conversation_id = convo.id
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.cookies.set(settings.csrf_cookie_name, csrf_token)
            client.headers[settings.csrf_header_name] = csrf_token

            response = client.patch(
                f"/api/chat/conversations/{conversation_id}",
                json={"title": "New Title"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "New Title"

        dispose_engine()

    def test_delete_conversation(self, monkeypatch, tmp_path):
        """Test deleting a conversation."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            user = _create_test_user(db)
            session_token, csrf_token = create_session(db, user)

            convo = Conversation(user_id=user.id, title="To Be Deleted")
            db.add(convo)
            db.commit()
            db.refresh(convo)
            conversation_id = convo.id
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.cookies.set(settings.csrf_cookie_name, csrf_token)
            client.headers[settings.csrf_header_name] = csrf_token

            response = client.delete(f"/api/chat/conversations/{conversation_id}")
            assert response.status_code == 200

            # Verify it's deleted
            get_response = client.get(f"/api/chat/conversations/{conversation_id}")
            assert get_response.status_code == 404

        dispose_engine()


class TestV1ChatAPI:
    """Tests for v1 chat API endpoints."""

    def test_v1_create_conversation(self, monkeypatch, tmp_path):
        """Test creating a conversation via v1 API."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            user = _create_test_user(db)
            session_token, csrf_token = create_session(db, user)
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.cookies.set(settings.csrf_cookie_name, csrf_token)
            client.headers[settings.csrf_header_name] = csrf_token

            response = client.post(
                "/v1/conversations",
                json={"title": "V1 Test Conversation", "provider": "lmstudio"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "V1 Test Conversation"
            assert "id" in data

        dispose_engine()

    def test_v1_list_conversations(self, monkeypatch, tmp_path):
        """Test listing conversations via v1 API."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            user = _create_test_user(db)
            session_token, csrf_token = create_session(db, user)

            # Create a conversation
            convo = Conversation(user_id=user.id, title="Test")
            db.add(convo)
            db.commit()
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.headers[settings.csrf_header_name] = csrf_token

            response = client.get("/v1/conversations")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) >= 1

        dispose_engine()

    def test_v1_get_conversation(self, monkeypatch, tmp_path):
        """Test getting a conversation via v1 API."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            user = _create_test_user(db)
            session_token, csrf_token = create_session(db, user)

            convo = Conversation(user_id=user.id, title="Test Conversation")
            db.add(convo)
            db.commit()
            db.refresh(convo)
            conversation_id = convo.id
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.headers[settings.csrf_header_name] = csrf_token

            response = client.get(f"/v1/conversations/{conversation_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == conversation_id

        dispose_engine()

    def test_v1_update_conversation(self, monkeypatch, tmp_path):
        """Test updating a conversation via v1 API."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            user = _create_test_user(db)
            session_token, csrf_token = create_session(db, user)

            convo = Conversation(user_id=user.id, title="Old Title")
            db.add(convo)
            db.commit()
            db.refresh(convo)
            conversation_id = convo.id
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.cookies.set(settings.csrf_cookie_name, csrf_token)
            client.headers[settings.csrf_header_name] = csrf_token

            response = client.patch(
                f"/v1/conversations/{conversation_id}",
                json={"title": "New Title", "settings": {"temperature": 0.5}}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "New Title"
            assert data["settings"]["temperature"] == 0.5

        dispose_engine()

    def test_v1_delete_conversation(self, monkeypatch, tmp_path):
        """Test deleting a conversation via v1 API."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            user = _create_test_user(db)
            session_token, csrf_token = create_session(db, user)

            convo = Conversation(user_id=user.id, title="To Delete")
            db.add(convo)
            db.commit()
            db.refresh(convo)
            conversation_id = convo.id
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.cookies.set(settings.csrf_cookie_name, csrf_token)
            client.headers[settings.csrf_header_name] = csrf_token

            response = client.delete(f"/v1/conversations/{conversation_id}")
            assert response.status_code == 200

            # Verify deletion
            get_response = client.get(f"/v1/conversations/{conversation_id}")
            assert get_response.status_code == 404

        dispose_engine()

    def test_v1_get_messages(self, monkeypatch, tmp_path):
        """Test getting messages via v1 API."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            user = _create_test_user(db)
            session_token, csrf_token = create_session(db, user)

            convo = Conversation(user_id=user.id, title="Test Conversation")
            db.add(convo)
            db.commit()
            db.refresh(convo)
            conversation_id = convo.id
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.headers[settings.csrf_header_name] = csrf_token

            response = client.get(f"/v1/conversations/{conversation_id}/messages")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

        dispose_engine()

    def test_v1_send_message_non_streaming(self, monkeypatch, tmp_path):
        """Test sending a message via v1 API (non-streaming)."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            user = _create_test_user(db)
            session_token, csrf_token = create_session(db, user)

            convo = Conversation(user_id=user.id, title="Test Conversation")
            db.add(convo)
            db.commit()
            db.refresh(convo)
            conversation_id = convo.id
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.cookies.set(settings.csrf_cookie_name, csrf_token)
            client.headers[settings.csrf_header_name] = csrf_token

            response = client.post(
                f"/v1/conversations/{conversation_id}/messages",
                json={"content": "Hello!", "stream": False}
            )
            assert response.status_code == 200
            data = response.json()
            assert "message" in data
            assert data["message"]["role"] == "assistant"

        dispose_engine()


class TestChatStreaming:
    """Tests for chat streaming functionality."""

    def test_v1_create_chat_run(self, monkeypatch, tmp_path):
        """Test creating a chat run via v1 API."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            user = _create_test_user(db)
            session_token, csrf_token = create_session(db, user)

            convo = Conversation(user_id=user.id, title="Test Conversation")
            db.add(convo)
            db.commit()
            db.refresh(convo)
            conversation_id = convo.id
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.cookies.set(settings.csrf_cookie_name, csrf_token)
            client.headers[settings.csrf_header_name] = csrf_token

            response = client.post(
                "/v1/chat",
                json={
                    "conversation_id": conversation_id,
                    "input": "Hello, AI!",
                    "stream": True
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert "run_id" in data
            assert data["status"] == "running"

        dispose_engine()

    def test_v1_cancel_chat_run(self, monkeypatch, tmp_path):
        """Test cancelling a chat run."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            user = _create_test_user(db)
            session_token, csrf_token = create_session(db, user)

            convo = Conversation(user_id=user.id, title="Test Conversation")
            db.add(convo)
            db.commit()
            db.refresh(convo)
            conversation_id = convo.id
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.cookies.set(settings.csrf_cookie_name, csrf_token)
            client.headers[settings.csrf_header_name] = csrf_token

            # Create a chat run
            run_response = client.post(
                "/v1/chat",
                json={
                    "conversation_id": conversation_id,
                    "input": "Hello, AI!",
                    "stream": True
                }
            )
            run_id = run_response.json()["run_id"]

            # Cancel the run
            response = client.post(
                "/v1/chat/cancel",
                json={"run_id": run_id}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "cancelled"
            assert data["run_id"] == run_id

        dispose_engine()


class TestChatAuthorization:
    """Tests for chat API authorization."""

    def test_list_conversations_requires_auth(self, monkeypatch, tmp_path):
        """Test that listing conversations requires authentication."""
        engine = _setup_db(tmp_path, monkeypatch)
        get_settings()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            response = client.get("/api/chat/conversations")
            assert response.status_code == 401

        dispose_engine()

    def test_create_conversation_requires_auth(self, monkeypatch, tmp_path):
        """Test that creating a conversation requires authentication."""
        engine = _setup_db(tmp_path, monkeypatch)
        get_settings()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            response = client.post(
                "/api/chat/conversations",
                json={"title": "Test"}
            )
            assert response.status_code == 401

        dispose_engine()

    def test_user_cannot_access_other_user_conversation(self, monkeypatch, tmp_path):
        """Test that users cannot access other users' conversations."""
        engine = _setup_db(tmp_path, monkeypatch)
        settings = get_settings()
        db = _get_session(engine)

        try:
            # Create two users
            user1 = User(
                email="user1@example.com",
                username="user1",
                hashed_password="hashed",
                is_active=True
            )
            user2 = User(
                email="user2@example.com",
                username="user2",
                hashed_password="hashed",
                is_active=True
            )
            db.add(user1)
            db.add(user2)
            db.commit()
            db.refresh(user1)
            db.refresh(user2)

            # Create a conversation for user2
            convo = Conversation(user_id=user2.id, title="User2's Conversation")
            db.add(convo)
            db.commit()
            db.refresh(convo)
            conversation_id = convo.id

            # Create session for user1
            session_token, csrf_token = create_session(db, user1)
        finally:
            db.close()

        app = create_app()
        _create_mock_provider_registry(app)

        with TestClient(app) as client:
            client.cookies.set(settings.session_cookie_name, session_token)
            client.headers[settings.csrf_header_name] = csrf_token

            # Try to access user2's conversation as user1
            response = client.get(f"/api/chat/conversations/{conversation_id}")
            assert response.status_code == 404

        dispose_engine()
