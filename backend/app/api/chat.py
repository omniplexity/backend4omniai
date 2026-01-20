from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.auth.csrf import require_csrf
from backend.app.auth.deps import require_active_user
from backend.app.config.settings import settings
from backend.app.db.models import Conversation, User
from backend.app.db.session import get_db
from backend.app.providers.registry import registry
from backend.app.providers.types import StreamEvent
from backend.app.services.chat_service import (
    append_assistant_message_service,
    append_user_message_service,
    list_messages_service,
)
from backend.app.services.generation_manager import generation_manager
from backend.app.services.quota_service import check_message_quota, increment_message_usage, add_token_usage
from backend.app.services.rate_limit import rate_limiter
from fastapi import Request

logger = logging.getLogger("backend")


class AppendMessageRequest(BaseModel):
    content: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"content": "Hello, how can you help me today?"}
            ]
        }
    }


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


router = APIRouter()


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
    increment_message_usage(db, user.id)
    db.commit()
    return {
        "message_id": message.id,
        "conversation_id": conversation_id,
    }


@router.post("/conversations/{conversation_id}/stream", dependencies=[Depends(require_csrf)])
def stream_chat(
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

    # Check ownership
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id, Conversation.user_id == user.id
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail={"code": "CONVERSATION_NOT_FOUND", "message": "Conversation not found"})

    # Get provider
    provider = registry.get(req.provider_id)

    # Check if model is available
    if not any(m.id == req.model for m in provider.list_models()):
        raise HTTPException(status_code=400, detail={"code": "MODEL_NOT_FOUND", "message": f"Model {req.model} not found for provider {req.provider_id}"})

    return StreamingResponse(
        stream_chat_generator(conversation_id, req.provider_id, req.model, req.temperature, req.top_p, req.max_tokens, user, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        },
    )


async def stream_chat_generator(
    conversation_id: int,
    provider_id: str,
    model: str,
    temperature: float | None,
    top_p: float | None,
    max_tokens: int | None,
    user: User,
    db: Session,
) -> AsyncGenerator[str, None]:
    """Generate SSE events for chat streaming."""
    generation_id = str(uuid.uuid4())
    last_heartbeat = time.time()
    assistant_content = ""
    provider_meta = None
    token_usage = None

    try:
        # Get conversation messages
        messages = list_messages_service(db, user.id, conversation_id)
        context = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        # Build request
        request = {
            "model": model,
            "messages": context,
            "stream": True,
        }
        if temperature is not None:
            request["temperature"] = temperature
        if top_p is not None:
            request["top_p"] = top_p
        if max_tokens is not None:
            request["max_tokens"] = max_tokens

        # Start generation tracking
        task = asyncio.create_task(_consume_stream(
            provider_id, request, generation_id, user, conversation_id, db
        ))
        await generation_manager.start_generation(
            generation_id, user.id, conversation_id, provider_id, model, task
        )

        logger.info("Chat generation started", extra={"generation_id": generation_id, "user_id": user.id, "conversation_id": conversation_id, "provider_id": provider_id, "model": model})

        # Send initial ping
        yield f"event: ping\ndata: {json.dumps({'ts': time.time()})}\n\n"
        last_heartbeat = time.time()

        # Stream from provider
        provider = registry.get(provider_id)
        async for event in provider.chat_stream(request):
            # Check for cancellation
            if generation_manager.is_canceled(generation_id):
                yield f"event: done\ndata: {json.dumps({'generation_id': generation_id, 'status': 'canceled'})}\n\n"
                return

            if event.type == "delta":
                assistant_content += event.delta or ""
                yield f"event: delta\ndata: {json.dumps({'generation_id': generation_id, 'delta': event.delta})}\n\n"

            elif event.type == "usage":
                token_usage = event.usage
                yield f"event: usage\ndata: {json.dumps({'generation_id': generation_id, 'usage': event.usage})}\n\n"

            elif event.type == "done":
                break

            # Send heartbeat if needed
            now = time.time()
            if now - last_heartbeat >= settings.sse_heartbeat_seconds:
                yield f"event: ping\ndata: {json.dumps({'ts': now})}\n\n"
                last_heartbeat = now

        # Send done event
        yield f"event: done\ndata: {json.dumps({'generation_id': generation_id, 'status': 'ok'})}\n\n"

        # Persist assistant message
        if assistant_content:
            message = append_assistant_message_service(
                db, user.id, conversation_id, assistant_content, provider_meta, token_usage
            )
            # Add token usage if available (only for successful generations)
            if token_usage and "total_tokens" in token_usage:
                add_token_usage(db, user.id, token_usage["total_tokens"])
            db.commit()

    except Exception as e:
        # Send error event
        yield f"event: error\ndata: {json.dumps({'generation_id': generation_id, 'code': 'STREAM_ERROR', 'message': str(e)})}\n\n"
        yield f"event: done\ndata: {json.dumps({'generation_id': generation_id, 'status': 'error'})}\n\n"

    finally:
        # Cleanup
        await generation_manager.cleanup_generation(generation_id)


async def _consume_stream(
    provider_id: str, request: dict, generation_id: str, user: User, conversation_id: int, db: Session
) -> None:
    """Consume the stream to ensure it completes (for task tracking)."""
    provider = registry.get(provider_id)
    async for _ in provider.chat_stream(request):
        if generation_manager.is_canceled(generation_id):
            break


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