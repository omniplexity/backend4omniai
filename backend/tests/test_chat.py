"""
Tests for chat orchestration (streaming, cancellation, retry, and error mapping).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.auth.password import hash_password
from app.config import get_settings
from app.core import ErrorCode, NotFoundError, QuotaExceededError, RateLimitError
from app.db.repositories import (
    create_conversation,
    create_user,
    get_conversation_messages,
    get_usage_counter,
    get_user_by_username,
    increment_usage_counter,
    update_user_quota,
)
from app.providers.base import (
    BaseProvider,
    ChatChunk,
    ProviderCapabilities,
    ProviderType,
)
from app.services.chat_service import ChatService


class MockProvider(BaseProvider):
    """Simple provider stub that yields predefined chunk sequences."""

    def __init__(
        self,
        responses: list[list[ChatChunk | Exception]],
        provider_type: ProviderType = ProviderType.OPENAI_COMPAT,
        chunk_delay: float = 0.0,
    ):
        self.provider_type = provider_type
        self._responses = responses
        self._call_count = 0
        self._chunk_delay = chunk_delay

    async def healthcheck(self) -> bool:
        return True

    async def list_models(self) -> list[Any]:
        return []

    async def capabilities(self, model: str | None = None) -> ProviderCapabilities:
        return ProviderCapabilities()

    async def chat_once(self, request: Any) -> Any:
        return None

    async def chat_stream(self, request: Any) -> AsyncGenerator[ChatChunk, None]:
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        for step in self._responses[idx]:
            if self._chunk_delay:
                await asyncio.sleep(self._chunk_delay)
            else:
                await asyncio.sleep(0)
            if isinstance(step, Exception):
                raise step
            yield step


class DummyRegistry:
    """Provider registry stub used by ChatService tests."""

    def __init__(self, provider: BaseProvider):
        self._provider = provider

    def get(self, provider_id: str) -> BaseProvider:
        if provider_id != self._provider.provider_type.value:
            raise NotFoundError(f"Provider '{provider_id}' not found")
        return self._provider

    async def aclose(self) -> None:
        """No-op close for dummy registry."""
        return None


def create_user_and_conversation(db: Session) -> tuple[str, str, str, str]:
    username = f"chatuser-{uuid.uuid4().hex[:6]}"
    password = "TestPass123"
    user = get_user_by_username(db, username)
    if not user:
        user = create_user(
            db,
            username=username,
            password_hash=hash_password(password),
            status="active",
        )
    conversation = create_conversation(db, user.id, title="Test chat")
    return user.id, conversation.id, username, password


def attach_provider(app, provider: BaseProvider) -> None:
    app.state.provider_registry = DummyRegistry(provider)
    app.state.chat_service = None


def parse_sse(raw: str) -> tuple[str | None, dict[str, Any]]:
    """Parse a single SSE message string."""
    normalized = raw.replace("\\n", "\n").strip()
    event = None
    data_lines: list[str] = []
    for line in normalized.splitlines():
        if line.startswith("event:"):
            event = line.split("event:", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split("data:", 1)[1].strip())
    payload = json.loads("".join(data_lines)) if data_lines else {}
    return event, payload



@pytest.mark.asyncio
async def test_chat_service_streams_and_persists_messages(
    chat_db_session: Session,
) -> None:
    user_id, conversation_id, _, _ = create_user_and_conversation(chat_db_session)
    provider = MockProvider(
        responses=[
            [
                ChatChunk(content="Hello ", finish_reason=None),
                ChatChunk(content="world", finish_reason="stop"),
            ]
        ]
    )
    service = ChatService(DummyRegistry(provider))
    request_id = str(uuid.uuid4())

    stream = await service.stream_chat(
        db=chat_db_session,
        user_id=user_id,
        conversation_id=conversation_id,
        provider_id=provider.provider_type.value,
        model="test-model",
        user_input="Hi",
        settings={"temperature": 0.5},
        request_id=request_id,
    )
    meta_seen = False
    delta_seen = False
    final_payload = None
    async for raw in stream:
        event, payload = parse_sse(raw)
        print("raw", raw.strip(), "parsed event", repr(event))
        if event == "meta":
            meta_seen = True
        elif event == "delta":
            delta_seen = True
        elif event == "final":
            final_payload = payload
            break

    assert meta_seen
    assert delta_seen
    assert final_payload is not None
    assert final_payload["provider_meta"]["request_id"] == request_id

    messages = get_conversation_messages(chat_db_session, conversation_id)
    assert len(messages) == 2
    assert messages[-1].content == "Hello world"


@pytest.mark.asyncio
async def test_chat_service_emits_keepalive_ping(
    chat_db_session: Session,
) -> None:
    user_id, conversation_id, _, _ = create_user_and_conversation(chat_db_session)
    settings = get_settings()
    original_interval = settings.sse_ping_interval_seconds
    settings.sse_ping_interval_seconds = 0.05
    provider = MockProvider(
        responses=[
            [ChatChunk(content="Slow response", finish_reason="stop")],
        ],
        chunk_delay=0.2,
    )
    service = ChatService(DummyRegistry(provider))

    ping_seen = False
    try:
        stream = await service.stream_chat(
            db=chat_db_session,
            user_id=user_id,
            conversation_id=conversation_id,
            provider_id=provider.provider_type.value,
            model="ping-model",
            user_input="Wait",
            settings=None,
            request_id=str(uuid.uuid4()),
        )
        async for raw in stream:
            if raw.strip() == ": ping":
                ping_seen = True
            event, payload = parse_sse(raw)
            if event == "final":
                break
    finally:
        settings.sse_ping_interval_seconds = original_interval

    assert ping_seen


@pytest.mark.asyncio
async def test_chat_service_cancel_stream(chat_db_session: Session) -> None:
    user_id, conversation_id, _, _ = create_user_and_conversation(chat_db_session)
    provider = MockProvider(
        responses=[
            [
                ChatChunk(content="Partial ", finish_reason=None),
                ChatChunk(content="text", finish_reason=None),
            ]
        ]
    )
    service = ChatService(DummyRegistry(provider))

    stream = await service.stream_chat(
        db=chat_db_session,
        user_id=user_id,
        conversation_id=conversation_id,
        provider_id=provider.provider_type.value,
        model="text-model",
        user_input="Partial",
        settings=None,
        request_id=str(uuid.uuid4()),
    )

    stream_id = None
    cancel_task: asyncio.Task | None = None
    try:
        async for raw in stream:
            event, payload = parse_sse(raw)
            if event == "meta":
                stream_id = payload["stream_id"]
            elif event == "delta" and stream_id and cancel_task is None:
                cancel_task = asyncio.create_task(
                    service.cancel_stream(stream_id, user_id)
                )
    except asyncio.CancelledError:
        pass
    finally:
        if cancel_task:
            await cancel_task


    messages = get_conversation_messages(chat_db_session, conversation_id)
    assert messages[-1].provider_meta
    meta = json.loads(messages[-1].provider_meta)
    assert meta["canceled"] is True


@pytest.mark.asyncio
async def test_chat_service_retry_last_turn(chat_db_session: Session) -> None:
    user_id, conversation_id, _, _ = create_user_and_conversation(chat_db_session)
    provider = MockProvider(
        responses=[
            [ChatChunk(content="First response", finish_reason="stop")],
            [ChatChunk(content="Retry response", finish_reason="stop")],
        ]
    )
    service = ChatService(DummyRegistry(provider))

    # Initial stream
    stream = await service.stream_chat(
        db=chat_db_session,
        user_id=user_id,
        conversation_id=conversation_id,
        provider_id=provider.provider_type.value,
        model="test-model",
        user_input="Hello",
        settings=None,
        request_id=str(uuid.uuid4()),
    )
    async for raw in stream:
        event, payload = parse_sse(raw)
        if event == "final":
            break

    initial_messages = get_conversation_messages(chat_db_session, conversation_id)
    assert len(initial_messages) == 2

    retry_stream = await service.retry_last_turn(
        db=chat_db_session,
        user_id=user_id,
        conversation_id=conversation_id,
        request_id=str(uuid.uuid4()),
    )
    retry_final = None
    async for raw in retry_stream:
        event, payload = parse_sse(raw)
        if event == "final":
            retry_final = payload
            break

    assert retry_final is not None
    post_messages = get_conversation_messages(chat_db_session, conversation_id)
    assert len(post_messages) == 4


@pytest.mark.asyncio
async def test_chat_service_rate_limit_error_as_event(chat_db_session: Session) -> None:
    user_id, conversation_id, _, _ = create_user_and_conversation(chat_db_session)
    provider = MockProvider(responses=[[RateLimitError("Rate limit")]])
    service = ChatService(DummyRegistry(provider))

    stream = await service.stream_chat(
        db=chat_db_session,
        user_id=user_id,
        conversation_id=conversation_id,
        provider_id=provider.provider_type.value,
        model="test-model",
        user_input="Trigger",
        settings=None,
        request_id=str(uuid.uuid4()),
    )

    error_payload = None
    async for raw in stream:
        event, payload = parse_sse(raw)
        if event == "error":
            error_payload = payload
            break

    assert error_payload is not None
    assert error_payload["code"] == ErrorCode.RATE_LIMITED.value
    messages = get_conversation_messages(chat_db_session, conversation_id)
    provider_meta = json.loads(messages[-1].provider_meta)
    assert provider_meta["error"]["code"] == ErrorCode.RATE_LIMITED.value


@pytest.mark.asyncio
async def test_usage_counter_increments_on_success(chat_db_session: Session) -> None:
    user_id, conversation_id, _, _ = create_user_and_conversation(chat_db_session)
    provider = MockProvider(
        responses=[[ChatChunk(content="OK", finish_reason="stop")]]
    )
    service = ChatService(DummyRegistry(provider))

    stream = await service.stream_chat(
        db=chat_db_session,
        user_id=user_id,
        conversation_id=conversation_id,
        provider_id=provider.provider_type.value,
        model="usage-model",
        user_input="Ping",
        settings=None,
        request_id=str(uuid.uuid4()),
    )
    async for raw in stream:
        event, _ = parse_sse(raw)
        if event == "final":
            break

    counter = get_usage_counter(chat_db_session, user_id)
    assert counter is not None and counter.messages_used == 1


@pytest.mark.asyncio
async def test_usage_counter_not_incremented_on_cancel(chat_db_session: Session) -> None:
    user_id, conversation_id, _, _ = create_user_and_conversation(chat_db_session)
    provider = MockProvider(
        responses=[
            [
                ChatChunk(content="Partial", finish_reason=None),
                ChatChunk(content="text", finish_reason=None),
            ]
        ]
    )
    service = ChatService(DummyRegistry(provider))

    stream = await service.stream_chat(
        db=chat_db_session,
        user_id=user_id,
        conversation_id=conversation_id,
        provider_id=provider.provider_type.value,
        model="cancel-model",
        user_input="Cancel",
        settings=None,
        request_id=str(uuid.uuid4()),
    )
    stream_id: str | None = None
    cancel_task: asyncio.Task | None = None
    try:
        async for raw in stream:
            event, payload = parse_sse(raw)
            if event == "meta":
                stream_id = payload["stream_id"]
            elif event == "delta" and stream_id and cancel_task is None:
                cancel_task = asyncio.create_task(
                    service.cancel_stream(stream_id, user_id)
                )
    finally:
        if cancel_task:
            await cancel_task

    counter = get_usage_counter(chat_db_session, user_id)
    assert counter is None or counter.messages_used == 0


@pytest.mark.asyncio
async def test_quota_blocks_stream(chat_db_session: Session) -> None:
    user_id, conversation_id, _, _ = create_user_and_conversation(chat_db_session)
    update_user_quota(
        chat_db_session,
        user_id,
        messages_per_day=1,
        tokens_per_day=None,
    )
    increment_usage_counter(chat_db_session, user_id, messages=1, tokens=0)
    provider = MockProvider(
        responses=[[ChatChunk(content="Denied", finish_reason="stop")]]
    )
    service = ChatService(DummyRegistry(provider))

    with pytest.raises(QuotaExceededError) as exc_info:
        await service.stream_chat(
            db=chat_db_session,
            user_id=user_id,
            conversation_id=conversation_id,
            provider_id=provider.provider_type.value,
            model="quota-model",
            user_input="Check quota",
            settings=None,
            request_id=str(uuid.uuid4()),
        )
    assert exc_info.value.code == ErrorCode.QUOTA_EXCEEDED


def test_increment_usage_counter_respects_date(chat_db_session: Session) -> None:
    user_id, _, _, _ = create_user_and_conversation(chat_db_session)
    previous_day = (datetime.now(UTC) - timedelta(days=1)).date()
    counter = increment_usage_counter(
        chat_db_session,
        user_id,
        messages=1,
        tokens=0,
        target_date=previous_day,
    )
    assert counter.date == previous_day
