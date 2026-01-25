from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.auth.csrf import require_csrf
from backend.app.auth.deps import require_active_user
from backend.app.config.settings import settings
from backend.app.db.models import Conversation, Project, User
from backend.app.db.session import get_db
from backend.app.providers.registry import registry
from backend.app.providers.types import StreamEvent
from backend.app.services.chat_service import (
    append_assistant_message_service,
    append_user_message_service,
    list_messages_service,
)
from backend.app.domain.services.conversation_service import ensure_conversation
from backend.app.domain.services.model_selection import ModelSelectionError, select_provider_model
from backend.app.services.memory_service import (
    build_memory_prompt,
    ingest_assistant_message,
    ingest_user_message,
)
from backend.app.services.generation_manager import generation_manager
from backend.app.services.quota_service import check_message_quota, increment_message_usage, add_token_usage
from backend.app.services.rate_limit import rate_limiter
logger = logging.getLogger("backend")

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Content-Type": "text/event-stream",
    "X-Accel-Buffering": "no",
}


class AppendMessageRequest(BaseModel):
    content: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"content": "Hello, how can you help me today?"}
            ]
        }
    }


class ChatMessage(BaseModel):
    role: str = "user"
    content: str


class StreamChatRequest(BaseModel):
    provider_id: str
    model: str
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "provider_id": "lmstudio",
                    "model": "llama-3.2-3b-instruct",
                    "temperature": 0.7,
                    "max_tokens": 1000
                }
            ]
        }
    }


class StreamChatRequestV2(BaseModel):
    conversation_id: int | None = None
    project_id: int | None = None
    message: ChatMessage
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None

class RetryChatRequest(BaseModel):
    conversation_id: int
    provider_id: str
    model: str
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "conversation_id": 123,
                    "provider_id": "lmstudio",
                    "model": "llama-3.2-3b-instruct",
                    "temperature": 0.7,
                    "max_tokens": 1000
                }
            ]
        }
    }


def check_rate_limits(request: Request, user: User) -> None:
    """Check IP and user rate limits."""
    client_ip = request.client.host if request.client else "unknown"
    rate_limiter.check_ip_rate(client_ip)
    rate_limiter.check_user_rate(user.id)


def _sse_event(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def _meta_payload(
    conversation_id: int,
    project_id: int | None,
    provider_id: str | None,
    model: str | None,
    generation_id: str,
) -> dict:
    return {
        "conversation_id": conversation_id,
        "project_id": project_id,
        "provider": provider_id,
        "model": model,
        "generation_id": generation_id,
    }


def _resolve_project(db: Session, user_id: int, conversation: Conversation, project_id: int | None) -> Project | None:
    target_id = project_id or conversation.project_id
    if not target_id:
        return None
    return db.query(Project).filter(Project.id == target_id, Project.user_id == user_id).first()


async def _error_stream(meta: dict, code: str, message: str) -> AsyncGenerator[str, None]:
    yield _sse_event("meta", meta)
    yield _sse_event("error", {"code": code, "message": message, "generation_id": meta.get("generation_id")})
    yield _sse_event("done", {"status": "error", "generation_id": meta.get("generation_id")})


router = APIRouter()


@router.post("/chat/stream", dependencies=[Depends(require_csrf)])
async def stream_chat_v2(
    req: StreamChatRequestV2,
    request: Request,
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream chat response with backend-enforced conversation/model selection."""
    check_rate_limits(request, user)
    check_message_quota(db, user.id)

    conversation = ensure_conversation(
        db,
        user.id,
        conversation_id=req.conversation_id,
        project_id=req.project_id,
    )
    project = _resolve_project(db, user.id, conversation, req.project_id)

    generation_id = str(uuid.uuid4())
    project_id = project.id if project else conversation.project_id
    meta_provider = req.provider or conversation.provider
    meta_model = req.model or conversation.model
    meta = _meta_payload(conversation.id, project_id, meta_provider, meta_model, generation_id)

    if req.message.role != "user":
        db.commit()
        return StreamingResponse(
            _error_stream(meta, "invalid_message", "Only user messages can be streamed"),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    message_content = (req.message.content or "").strip()
    if not message_content:
        db.commit()
        return StreamingResponse(
            _error_stream(meta, "invalid_message", "Message content is required"),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    try:
        provider_id, model = await select_provider_model(
            user,
            project,
            conversation,
            requested_provider=req.provider,
            requested_model=req.model,
        )
    except ModelSelectionError as exc:
        db.commit()
        return StreamingResponse(
            _error_stream(meta, exc.code, exc.message),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    # Pin defaults on first use
    if not conversation.provider or not conversation.model:
        conversation.provider = provider_id
        conversation.model = model
    if req.project_id and conversation.project_id is None and project:
        conversation.project_id = project.id

    append_user_message_service(db, user.id, conversation.id, message_content)
    if settings.memory_enabled and settings.memory_auto_ingest_user_messages:
        try:
            ingest_user_message(db, user.id, conversation.id, message_content)
        except Exception:
            logger.warning("Memory ingest failed", extra={"user_id": user.id, "conversation_id": conversation.id})
    increment_message_usage(db, user.id)
    db.commit()

    return StreamingResponse(
        stream_chat_generator(
            conversation.id,
            project_id,
            provider_id,
            model,
            req.temperature,
            req.top_p,
            req.max_tokens,
            user,
            db,
            generation_id,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/conversations/{conversation_id}/messages", dependencies=[Depends(require_csrf)])
def append_message(
    conversation_id: int,
    req: AppendMessageRequest,
    request: Request = None,
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> dict:
    """Append a user message to a conversation."""
    # Check rate limits
    check_rate_limits(request, user)

    # Check quota
    check_message_quota(db, user.id)

    # Check ownership
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id, Conversation.user_id == user.id
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"})

    message = append_user_message_service(db, user.id, conversation_id, req.content)
    if settings.memory_enabled and settings.memory_auto_ingest_user_messages:
        try:
            ingest_user_message(db, user.id, conversation_id, req.content)
        except Exception:
            logger.warning("Memory ingest failed", extra={"user_id": user.id, "conversation_id": conversation_id})
    increment_message_usage(db, user.id)
    db.commit()
    return {
        "message_id": message.id,
        "conversation_id": conversation_id,
    }


@router.post("/conversations/{conversation_id}/stream", dependencies=[Depends(require_csrf)])
async def stream_chat(
    conversation_id: int,
    req: StreamChatRequest,
    request: Request = None,
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream chat response for a conversation."""
    # Check rate limits and quota
    check_rate_limits(request, user)
    check_message_quota(db, user.id)

    conversation = ensure_conversation(db, user.id, conversation_id=conversation_id)
    project = _resolve_project(db, user.id, conversation, None)

    generation_id = str(uuid.uuid4())
    project_id = project.id if project else conversation.project_id
    meta_provider = req.provider_id or conversation.provider
    meta_model = req.model or conversation.model
    meta = _meta_payload(conversation.id, project_id, meta_provider, meta_model, generation_id)

    try:
        provider_id, model = await select_provider_model(
            user,
            project,
            conversation,
            requested_provider=req.provider_id,
            requested_model=req.model,
        )
    except ModelSelectionError as exc:
        db.commit()
        return StreamingResponse(
            _error_stream(meta, exc.code, exc.message),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    if not conversation.provider or not conversation.model:
        conversation.provider = provider_id
        conversation.model = model
    db.commit()

    return StreamingResponse(
        stream_chat_generator(
            conversation.id,
            project_id,
            provider_id,
            model,
            req.temperature,
            req.top_p,
            req.max_tokens,
            user,
            db,
            generation_id,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


async def stream_chat_generator(
    conversation_id: int,
    project_id: int | None,
    provider_id: str,
    model: str,
    temperature: float | None,
    top_p: float | None,
    max_tokens: int | None,
    user: User,
    db: Session,
    generation_id: str,
) -> AsyncGenerator[str, None]:
    """Generate SSE events for chat streaming."""
    last_heartbeat = time.time()
    start_time = time.time()
    assistant_content = ""
    provider_meta = None
    token_usage = None

    generation_done = asyncio.Event()
    tracking_task = asyncio.create_task(generation_done.wait())
    await generation_manager.start_generation(
        generation_id, user.id, conversation_id, provider_id, model, tracking_task
    )

    try:
        # Send meta first
        yield _sse_event(
            "meta",
            _meta_payload(conversation_id, project_id, provider_id, model, generation_id),
        )

        # Get conversation messages
        messages = list_messages_service(db, user.id, conversation_id)
        context = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        # Build request with optional memory context
        memory_prompt = ""
        if settings.memory_enabled:
            try:
                last_user_message = None
                for msg in reversed(messages):
                    if msg.role == "user":
                        last_user_message = msg.content
                        break
                if last_user_message:
                    memory_prompt = build_memory_prompt(
                        db,
                        user.id,
                        last_user_message,
                        limit=settings.memory_top_k,
                    )
            except Exception:
                logger.warning("Memory lookup failed", extra={"user_id": user.id, "conversation_id": conversation_id})

        request = {
            "model": model,
            "messages": ([{"role": "system", "content": memory_prompt}] + context) if memory_prompt else context,
            "stream": True,
        }
        if temperature is not None:
            request["temperature"] = temperature
        if top_p is not None:
            request["top_p"] = top_p
        if max_tokens is not None:
            request["max_tokens"] = max_tokens

        logger.info("Chat generation started", extra={"generation_id": generation_id, "user_id": user.id, "conversation_id": conversation_id, "provider_id": provider_id, "model": model})

        # Send initial ping
        yield _sse_event("ping", {"ts": time.time()})
        last_heartbeat = time.time()

        # Stream from provider
        provider = registry.get(provider_id)
        async for event in provider.chat_stream(request):
            # Check for cancellation
            if generation_manager.is_canceled(generation_id):
                elapsed_ms = int((time.time() - start_time) * 1000)
                yield _sse_event(
                    "done",
                    {
                        "generation_id": generation_id,
                        "status": "canceled",
                        "elapsed_ms": elapsed_ms,
                        "usage": token_usage,
                    },
                )
                return

            if event.type == "delta":
                assistant_content += event.delta or ""
                yield _sse_event(
                    "delta",
                    {
                        "generation_id": generation_id,
                        "delta": event.delta,
                        "text": event.delta,
                    },
                )

            elif event.type == "usage":
                token_usage = event.usage
                yield _sse_event(
                    "usage",
                    {"generation_id": generation_id, "usage": event.usage},
                )

            elif event.type == "done":
                break

            # Send heartbeat if needed
            now = time.time()
            if now - last_heartbeat >= settings.sse_heartbeat_seconds:
                yield _sse_event("ping", {"ts": now})
                last_heartbeat = now

        # Send done event
        elapsed_ms = int((time.time() - start_time) * 1000)
        yield _sse_event(
            "done",
            {
                "generation_id": generation_id,
                "status": "ok",
                "usage": token_usage,
                "elapsed_ms": elapsed_ms,
            },
        )

        # Persist assistant message
        if assistant_content:
            message = append_assistant_message_service(
                db, user.id, conversation_id, assistant_content, provider_meta, token_usage
            )
            if settings.memory_auto_ingest_assistant_messages:
                try:
                    ingest_assistant_message(db, user.id, conversation_id, assistant_content)
                except Exception:
                    logger.warning("Assistant memory ingest failed", extra={"user_id": user.id, "conversation_id": conversation_id})
            # Add token usage if available (only for successful generations)
            if token_usage and "total_tokens" in token_usage:
                add_token_usage(db, user.id, token_usage["total_tokens"])
            db.commit()

    except Exception as exc:
        code = "provider_error"
        message = "Provider error"
        if isinstance(exc, HTTPException) and isinstance(exc.detail, dict):
            code = exc.detail.get("code", code)
            message = exc.detail.get("message", message)
        elapsed_ms = int((time.time() - start_time) * 1000)
        yield _sse_event(
            "error",
            {
                "generation_id": generation_id,
                "code": code,
                "message": message,
            },
        )
        yield _sse_event(
            "done",
            {
                "generation_id": generation_id,
                "status": "error",
                "usage": token_usage,
                "elapsed_ms": elapsed_ms,
            },
        )

    finally:
        # Cleanup
        generation_done.set()
        await generation_manager.cleanup_generation(generation_id)


@router.post("/chat/cancel/{generation_id}", dependencies=[Depends(require_csrf)])
async def cancel_generation(
    generation_id: str,
    user: User = Depends(require_active_user),
) -> dict:
    """Cancel an active generation."""
    canceled = await generation_manager.cancel_generation(generation_id, user.id)
    if not canceled:
        raise HTTPException(status_code=404, detail={"code": "GENERATION_NOT_FOUND", "message": "Generation not found or already completed"})
    return {"message": "Generation canceled"}


@router.post("/chat/retry", dependencies=[Depends(require_csrf)])
def retry_chat(
    req: RetryChatRequest,
    request: Request = None,
    user: User = Depends(require_active_user),
    db: Session = Depends(get_db),
) -> dict:
    """Retry the last user message in a conversation."""
    # Check rate limits
    check_rate_limits(request, user)

    # Check quota
    check_message_quota(db, user.id)

    # Check ownership
    conversation = db.query(Conversation).filter(
        Conversation.id == req.conversation_id, Conversation.user_id == user.id
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"})

    # Find last user message
    messages = list_messages_service(db, user.id, req.conversation_id)
    last_user_message = None
    for msg in reversed(messages):
        if msg.role == "user":
            last_user_message = msg
            break

    if not last_user_message:
        raise HTTPException(status_code=400, detail={"code": "NO_USER_MESSAGE", "message": "No user message found to retry"})

    # Re-append the user message (to ensure it's the latest)
    message = append_user_message_service(db, user.id, req.conversation_id, last_user_message.content)
    increment_message_usage(db, user.id)
    db.commit()

    return {
        "message_id": message.id,
        "conversation_id": req.conversation_id,
    }
