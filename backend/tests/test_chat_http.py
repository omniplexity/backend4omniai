"""HTTP-level tests for chat streaming and CSRF enforcement."""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.password import hash_password
from app.config import get_settings
from app.core import CSRFError, ErrorCode, NotFoundError
from app.db.repositories import create_conversation, create_user, update_user_status
from app.providers.base import (
    BaseProvider,
    ChatChunk,
    ChatRequest,
    ProviderCapabilities,
    ProviderType,
)


class BasicProvider(BaseProvider):
    """Simple provider stub that yields configured chunks."""

    def __init__(self, chunks: list[ChatChunk], provider_type: ProviderType):
        self.chunks = chunks
        self.provider_type = provider_type

    async def healthcheck(self) -> bool:
        return True

    async def list_models(self) -> list[Any]:
        return []

    async def capabilities(self, model: str | None = None) -> ProviderCapabilities:
        return ProviderCapabilities()

    async def chat_once(self, request: ChatRequest) -> Any:
        raise NotImplementedError("Not used in these tests")

    async def chat_stream(self, request: ChatRequest):
        for chunk in self.chunks:
            yield chunk


class DummyProviderRegistry:
    """Registry stub that always returns the configured provider."""

    def __init__(self, provider: BaseProvider):
        self.provider = provider

    def get(self, provider_id: str) -> BaseProvider:
        if provider_id != self.provider.provider_type.value:
            raise NotFoundError(f"Provider '{provider_id}' not found")
        return self.provider

    async def aclose(self) -> None:
        return None


class StubChatService:
    """Lightweight chat service used for cancellation tests."""

    def __init__(self) -> None:
        self.cancel_called_with: tuple[str, str] | None = None

    async def cancel_stream(self, stream_id: str, user_id: str) -> bool:
        self.cancel_called_with = (stream_id, user_id)
        return True


def create_user_with_session(
    client: TestClient,
    db: Session,
    username: str,
    password: str,
) -> tuple[str, str]:
    """Create a user and obtain a CSRF token via the login endpoint."""
    user = create_user(
        db,
        username=username,
        password_hash=hash_password(password),
        status="active",
    )
    response = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"], user.id


def attach_provider(client: TestClient, provider: BaseProvider) -> None:
    """Wire a custom provider into the app for streaming tests."""
    client.app.state.provider_registry = DummyProviderRegistry(provider)
    client.app.state.chat_service = None


def parse_sse(raw: str) -> tuple[str | None, dict[str, Any]]:
    """Parse a single SSE event payload."""
    event: str | None = None
    data_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("event:"):
            event = line.split("event:", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split("data:", 1)[1].strip())
    payload = json.loads("".join(data_lines)) if data_lines else {}
    return event, payload


def iter_sse_events(response: Any) -> list[tuple[str | None, dict[str, Any]]]:
    """Collect SSE events emitted by a streaming response."""
    raw = response.read()
    text = raw.decode("utf-8", errors="replace")
    text = text.replace("\\n", "\n")
    lines = text.splitlines()
    events: list[tuple[str | None, dict[str, Any]]] = []
    buffer: list[str] = []
    for line in lines:
        if line == "":
            if buffer:
                events.append(parse_sse("\n".join(buffer)))
                buffer = []
            continue
        buffer.append(line)
    if buffer:
        events.append(parse_sse("\n".join(buffer)))
    return events


def get_csrf_header_name() -> str:
    """Helper to read the configured CSRF header name."""
    return get_settings().csrf_header_name


def assert_meta_delta_final(events: list[tuple[str | None, dict[str, Any]]]) -> None:
    """Validate that meta/delta/final events were emitted in that order."""
    assert events, "Expected at least one SSE event"
    assert events[0][0] == "meta"
    assert any(event == "delta" for event, _ in events)
    assert events[-1][0] == "final"
    meta_payload = events[0][1]
    final_payload = events[-1][1]
    assert "stream_id" in meta_payload
    assert "conversation_id" in meta_payload
    assert "provider_id" in meta_payload
    assert "message_id" in final_payload
    provider_meta = final_payload.get("provider_meta", {})
    assert provider_meta.get("stream_id") == meta_payload.get("stream_id")


def login_and_prepare_conversation(
    client: TestClient, db: Session
) -> tuple[str, str, str]:
    """Create user, start session, and create a conversation."""
    password = "TestPass!123"
    username = f"chat-http-{uuid.uuid4().hex[:6]}"
    csrf_token, user_id = create_user_with_session(client, db, username, password)
    conversation = create_conversation(db, user_id)
    return csrf_token, user_id, conversation.id


def start_stream_request(
    client: TestClient,
    conversation_id: str,
    csrf_token: str,
) -> list[tuple[str | None, dict[str, Any]]]:
    """Helper to open a chat stream and collect SSE events."""
    payload = {
        "conversation_id": conversation_id,
        "provider_id": ProviderType.LMSTUDIO.value,
        "model": "http-test-model",
        "input": "Hello via HTTP",
    }
    headers = {get_csrf_header_name(): csrf_token}
    with client.stream(
        "POST",
        "/chat/stream",
        json=payload,
        headers=headers,
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "X-Request-ID" in response.headers
        events = iter_sse_events(response)
    return events


def test_chat_stream_sse_emits_meta_delta_final(
    chat_client: TestClient, chat_db_session: Session
) -> None:
    """Happy path: SSE emits meta/delta/final and X-Request-ID is preserved."""
    csrf_token, _, conversation_id = login_and_prepare_conversation(
        chat_client, chat_db_session
    )
    provider = BasicProvider(
        chunks=[
            ChatChunk(content="Hello", finish_reason=None),
            ChatChunk(content=" world", finish_reason="stop"),
        ],
        provider_type=ProviderType.LMSTUDIO,
    )
    attach_provider(chat_client, provider)
    events = start_stream_request(
        chat_client,
        conversation_id=conversation_id,
        csrf_token=csrf_token,
    )
    assert_meta_delta_final(events)


def test_chat_cancel_enforces_csrf(
    chat_client: TestClient, chat_db_session: Session
) -> None:
    """Cancel endpoint rejects requests without CSRF and accepts valid tokens."""
    csrf_token, _, _ = login_and_prepare_conversation(chat_client, chat_db_session)
    stub_service = StubChatService()
    chat_client.app.state.chat_service = stub_service

    # Missing CSRF header should raise an explicit CSRFError from middleware.
    with pytest.raises(CSRFError) as exc_info:
        chat_client.post("/chat/cancel", json={"stream_id": "fake"})
    assert exc_info.value.code == ErrorCode.CSRF_FAILED

    # Valid CSRF allows cancellation and returns success.
    headers = {get_csrf_header_name(): csrf_token}
    response = chat_client.post(
        "/chat/cancel", json={"stream_id": "fake"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_admin_routes_require_admin(chat_client: TestClient, chat_db_session: Session) -> None:
    """Admin endpoints should return 403 for non-admin users."""
    csrf_token, user_id, _ = login_and_prepare_conversation(
        chat_client, chat_db_session
    )
    # Use existing session (non-admin user)
    for path in ("/admin/users", "/admin/usage", "/admin/audit"):
        response = chat_client.get(path)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == ErrorCode.FORBIDDEN.value


def test_disabled_user_cannot_stream(chat_client: TestClient, chat_db_session: Session) -> None:
    """Disabled users are blocked from /chat/stream."""
    csrf_token, user_id, conversation_id = login_and_prepare_conversation(
        chat_client, chat_db_session
    )
    update_user_status(chat_db_session, user_id, "disabled")
    headers = {get_csrf_header_name(): csrf_token}
    payload = {
        "conversation_id": conversation_id,
        "provider_id": ProviderType.LMSTUDIO.value,
        "model": "ignore",
        "input": "Hello",
    }
    response = chat_client.post("/chat/stream", json=payload, headers=headers)
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == ErrorCode.ACCOUNT_DISABLED.value
