"""Chat orchestration service with SSE streaming, cancellation, and retries."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import (
    AppError,
    ErrorCode,
    NotFoundError,
    QuotaExceededError,
    ValidationError,
    get_logger,
    stream_id_ctx,
)
from app.core.metrics import metrics
from app.db.models import Conversation, Message
from app.db.repositories import (
    create_message,
    get_conversation_messages,
    get_last_assistant_message_after,
    get_last_user_message,
    get_usage_counter,
    get_user_conversation,
    get_user_quota,
    increment_usage_counter,
)
from app.providers import ProviderRegistry
from app.providers.base import ChatMessage, ChatRequest

logger = get_logger(__name__)


@dataclass
class ActiveStream:
    """Metadata for an in-flight chat stream."""

    stream_id: str
    user_id: str
    conversation_id: str
    started_at: datetime
    cancel_event: asyncio.Event
    task: asyncio.Task | None = None


class ActiveStreamManager:
    """Tracks active SSE streams so they can be cancelled."""

    def __init__(self) -> None:
        self._streams: dict[str, ActiveStream] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        stream_id: str,
        user_id: str,
        conversation_id: str,
        cancel_event: asyncio.Event,
        task: asyncio.Task | None,
    ) -> None:
        """Track a new stream."""
        async with self._lock:
            self._streams[stream_id] = ActiveStream(
                stream_id=stream_id,
                user_id=user_id,
                conversation_id=conversation_id,
                started_at=datetime.now(UTC),
                cancel_event=cancel_event,
                task=task,
            )
            metrics.set_gauge("active_streams", float(len(self._streams)))

    async def unregister(self, stream_id: str) -> ActiveStream | None:
        """Stop tracking a stream once it completes."""
        async with self._lock:
            stream = self._streams.pop(stream_id, None)
            metrics.set_gauge("active_streams", float(len(self._streams)))
        return stream

    async def cancel(self, stream_id: str, user_id: str) -> bool:
        """Signal cancellation for a running stream if it belongs to the requester."""
        async with self._lock:
            stream = self._streams.get(stream_id)
        if not stream or stream.user_id != user_id:
            return False
        stream.cancel_event.set()
        if stream.task and not stream.task.done():
            stream.task.cancel()
        return True

    async def get(self, stream_id: str) -> ActiveStream | None:
        """Retrieve stream metadata (unused yet)."""
        async with self._lock:
            return self._streams.get(stream_id)


class ChatService:
    """Handles chat streaming, persistence, cancellation, and retries."""

    def __init__(self, registry: ProviderRegistry):
        self.registry = registry
        self.manager = ActiveStreamManager()
        self.settings = get_settings()

    async def stream_chat(
        self,
        *,
        db: Session,
        user_id: str,
        conversation_id: str,
        provider_id: str,
        model: str,
        user_input: str,
        settings: dict[str, Any] | None,
        request_id: str | None,
    ) -> AsyncIterator[str]:
        """Stream a chat completion as SSE."""
        conversation = get_user_conversation(db, user_id, conversation_id)
        if not conversation:
            raise NotFoundError("Conversation not found")

        self._enforce_quota(db, user_id)

        history = get_conversation_messages(db, conversation_id)
        settings_dict = dict(settings or {})
        user_message = create_message(
            db,
            conversation_id=conversation_id,
            role="user",
            content=user_input,
        )
        base_meta = {
            "provider_id": provider_id,
            "model": model,
            "settings": settings_dict,
        }
        assistant_message = create_message(
            db,
            conversation_id=conversation_id,
            role="assistant",
            content="",
            provider=provider_id,
            model=model,
            provider_meta=json.dumps(base_meta),
        )

        chatlog = [
            ChatMessage(role=message.role, content=message.content)
            for message in history
        ]
        chatlog.append(ChatMessage(role=user_message.role, content=user_message.content))

        chat_request = ChatRequest(
            model=model,
            messages=chatlog,
            temperature=settings_dict.get("temperature", 0.7),
            max_tokens=settings_dict.get("max_tokens"),
            top_p=settings_dict.get("top_p"),
            stop=settings_dict.get("stop"),
            stream=True,
        )

        stream_id = str(uuid.uuid4())
        cancel_event = asyncio.Event()
        provider = self.registry.get(provider_id)
        ping_interval = float(self.settings.sse_ping_interval_seconds or 0)
        use_ping = ping_interval > 0

        async def event_generator() -> AsyncIterator[str]:
            task = asyncio.current_task()
            await self.manager.register(
                stream_id, user_id, conversation_id, cancel_event, task
            )
            stream_token = stream_id_ctx.set(stream_id)
            stream_meta: ActiveStream | None = None
            try:
                meta_payload = {
                    "stream_id": stream_id,
                    "conversation_id": conversation_id,
                    "provider_id": provider_id,
                    "model": model,
                    "request_id": request_id,
                }
                yield self._format_sse_event("meta", meta_payload)

                assistant_content = ""
                finish_reason: str | None = None
                resolved_model = model

                provider_iter = provider.chat_stream(chat_request).__aiter__()
                try:
                    while True:
                        if cancel_event.is_set():
                            raise asyncio.CancelledError()
                        try:
                            if use_ping:
                                chunk = await asyncio.wait_for(
                                    provider_iter.__anext__(), timeout=ping_interval
                                )
                            else:
                                chunk = await provider_iter.__anext__()
                        except TimeoutError:
                            # Emit lightweight comment pings so clients can keep idle connections alive.
                            metrics.increment("sse_pings_sent")
                            yield self._format_sse_comment()
                            continue
                        except StopAsyncIteration:
                            break
                        if chunk.model:
                            resolved_model = chunk.model
                        text = chunk.content or ""
                        if text:
                            assistant_content += text
                            yield self._format_sse_event("delta", {"text": text})
                        if chunk.finish_reason:
                            finish_reason = chunk.finish_reason
                        if cancel_event.is_set():
                            raise asyncio.CancelledError()
                except asyncio.CancelledError:
                    logger.info(
                        "Chat stream cancelled",
                        data={"stream_id": stream_id, "user_id": user_id},
                    )
                    base_meta["model"] = resolved_model
                    final_meta, token_usage = self._finalize_assistant_message(
                        db,
                        conversation,
                        assistant_message,
                        base_meta,
                        stream_id,
                        request_id,
                        assistant_content,
                        provider_id,
                        resolved_model,
                        user_id=user_id,
                        increment_usage=False,
                        canceled=True,
                        finish_reason=finish_reason,
                    )
                    payload = {
                        "message_id": assistant_message.id,
                        "provider_meta": final_meta,
                    }
                    if token_usage:
                        payload["token_usage"] = token_usage
                    yield self._format_sse_event("final", payload)
                    return

                base_meta["model"] = resolved_model
                final_meta, token_usage = self._finalize_assistant_message(
                    db,
                    conversation,
                    assistant_message,
                    base_meta,
                    stream_id,
                    request_id,
                    assistant_content,
                    provider_id,
                    resolved_model,
                    user_id=user_id,
                    increment_usage=True,
                    canceled=False,
                    finish_reason=finish_reason,
                )
                payload = {
                    "message_id": assistant_message.id,
                    "provider_meta": final_meta,
                }
                if token_usage:
                    payload["token_usage"] = token_usage
                yield self._format_sse_event("final", payload)
            except AppError as exc:
                logger.warning(
                    "Provider error during chat stream",
                    data={"stream_id": stream_id, "code": exc.code.value},
                )
                base_meta["model"] = resolved_model
                self._finalize_assistant_message(
                    db,
                    conversation,
                    assistant_message,
                    base_meta,
                    stream_id,
                    request_id,
                    assistant_content,
                    provider_id,
                    resolved_model,
                    user_id=user_id,
                    increment_usage=False,
                    canceled=False,
                    error=exc,
                )
                yield self._format_sse_event(
                    "error",
                    {
                        "code": exc.code.value,
                        "message": exc.message,
                        "request_id": request_id,
                    },
                )
                return
            except Exception as exc:
                logger.exception(
                    "Unexpected error during chat stream",
                    exc_info=exc,
                    data={"stream_id": stream_id},
                )
                base_meta["model"] = resolved_model
                app_error = AppError(
                    ErrorCode.INTERNAL_ERROR,
                    "An unexpected error occurred",
                    details={"provider_id": provider_id},
                )
                self._finalize_assistant_message(
                    db,
                    conversation,
                    assistant_message,
                    base_meta,
                    stream_id,
                    request_id,
                    assistant_content,
                    provider_id,
                    resolved_model,
                    user_id=user_id,
                    increment_usage=False,
                    canceled=False,
                    error=app_error,
                )
                yield self._format_sse_event(
                    "error",
                    {
                        "code": app_error.code.value,
                        "message": app_error.message,
                        "request_id": request_id,
                    },
                )
                return
            finally:
                stream_meta = await self.manager.unregister(stream_id)
                stream_id_ctx.reset(stream_token)
                if stream_meta:
                    elapsed = (datetime.now(UTC) - stream_meta.started_at).total_seconds()
                    metrics.observe("stream_duration_seconds", elapsed)

        return event_generator()

    async def retry_last_turn(
        self,
        *,
        db: Session,
        user_id: str,
        conversation_id: str,
        request_id: str | None,
    ) -> AsyncIterator[str]:
        """Retry the last user turn with the same provider settings."""
        conversation = get_user_conversation(db, user_id, conversation_id)
        if not conversation:
            raise NotFoundError("Conversation not found")

        last_user = get_last_user_message(db, conversation_id)
        if not last_user:
            raise ValidationError("No user message to retry")

        last_assistant = get_last_assistant_message_after(
            db, conversation_id, after=last_user.created_at
        )
        if not last_assistant or not last_assistant.provider_meta:
            raise ValidationError("Cannot retry without previous assistant metadata")

        try:
            meta = json.loads(last_assistant.provider_meta)
        except json.JSONDecodeError as exc:
            raise ValidationError("Invalid provider metadata for retry") from exc

        if not isinstance(meta, dict):
            raise ValidationError("Invalid provider metadata for retry")

        provider_id = meta.get("provider_id")
        model = meta.get("model")
        settings = meta.get("settings") if isinstance(meta.get("settings"), dict) else {}

        if not provider_id or not model:
            raise ValidationError("Provider metadata missing model or provider")

        return await self.stream_chat(
            db=db,
            user_id=user_id,
            conversation_id=conversation_id,
            provider_id=provider_id,
            model=model,
            user_input=last_user.content,
            settings=settings,
            request_id=request_id,
        )

    async def cancel_stream(self, stream_id: str, user_id: str) -> bool:
        """Cancel an active stream if it belongs to the requesting user."""
        return await self.manager.cancel(stream_id, user_id)

    @staticmethod
    def _format_sse_event(event: str, payload: dict[str, Any]) -> str:
        """Serialize an event to SSE format."""
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        return f"event: {event}\\ndata: {data}\\n\\n"

    @staticmethod
    def _format_sse_comment(comment: str = "ping") -> str:
        """Serialize an SSE comment (used for keep-alives)."""
        return f": {comment}\n\n"

    @staticmethod
    def _build_provider_meta(
        *,
        base_meta: dict[str, Any],
        stream_id: str,
        request_id: str | None,
        canceled: bool,
        finish_reason: str | None,
        error: AppError | None,
    ) -> dict[str, Any]:
        """Construct provider metadata stored with assistant messages."""
        meta = dict(base_meta)
        meta["stream_id"] = stream_id
        meta["request_id"] = request_id
        meta["canceled"] = canceled
        meta["completed"] = not canceled and error is None
        if finish_reason:
            meta["finish_reason"] = finish_reason
        if error:
            meta["error"] = {"code": error.code.value, "message": error.message}
            if error.details:
                meta["error_details"] = error.details
        return meta

    @staticmethod
    def _build_token_usage(message: Message) -> dict[str, int]:
        """Capture token counts if available."""
        usage: dict[str, int] = {}
        if message.prompt_tokens is not None:
            usage["prompt_tokens"] = message.prompt_tokens
        if message.completion_tokens is not None:
            usage["completion_tokens"] = message.completion_tokens
        if message.total_tokens is not None:
            usage["total_tokens"] = message.total_tokens
        return usage

    def _enforce_quota(self, db: Session, user_id: str) -> None:
        """Ensure user has remaining quota before streaming."""
        quota = get_user_quota(db, user_id)
        if not quota:
            return
        today = datetime.now(UTC).date()
        counter = get_usage_counter(db, user_id, today)
        messages_used = counter.messages_used if counter else 0
        tokens_used = counter.tokens_used if counter else 0
        if quota.messages_per_day is not None and messages_used >= quota.messages_per_day:
            metrics.increment("quota_blocks_total")
            raise QuotaExceededError(
                "Daily message quota exceeded",
                details={"user_id": user_id, "limit": quota.messages_per_day},
            )
        if quota.tokens_per_day is not None and tokens_used >= quota.tokens_per_day:
            metrics.increment("quota_blocks_total")
            raise QuotaExceededError(
                "Daily token quota exceeded",
                details={"user_id": user_id, "limit": quota.tokens_per_day},
            )

    def _finalize_assistant_message(
        self,
        db: Session,
        conversation: Conversation,
        message: Message,
        base_meta: dict[str, Any],
        stream_id: str,
        request_id: str | None,
        content: str,
        provider_id: str,
        model: str,
        *,
        user_id: str,
        increment_usage: bool = False,
        canceled: bool = False,
        finish_reason: str | None = None,
        error: AppError | None = None,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """Persist assistant response and metadata."""
        base_meta["model"] = model
        meta = self._build_provider_meta(
            base_meta=base_meta,
            stream_id=stream_id,
            request_id=request_id,
            canceled=canceled,
            finish_reason=finish_reason,
            error=error,
        )
        message.content = content
        message.provider = provider_id
        message.model = model
        message.provider_meta = json.dumps(meta)
        if increment_usage and not canceled and error is None:
            tokens = message.total_tokens or 0
            increment_usage_counter(db, user_id, messages=1, tokens=tokens)
        conversation.model = model
        db.commit()
        db.refresh(message)
        return meta, self._build_token_usage(message)
