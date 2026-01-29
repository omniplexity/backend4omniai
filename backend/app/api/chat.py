"""Chat and conversation endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import RequireAuth, ValidateCSRF
from app.config import get_settings
from app.core import NotFoundError
from app.core.logging import request_id_ctx
from app.db import get_db
from app.db.repositories import (
    create_conversation,
    delete_conversation,
    get_conversation_messages,
    get_user_conversation,
    list_user_conversations,
    update_conversation_title,
)
from app.providers import ProviderRegistry
from app.services.chat_service import ChatService

router = APIRouter(tags=["chat"])


class CreateConversationRequest(BaseModel):
    title: str | None = Field(None, max_length=255)


class ConversationResponse(BaseModel):
    id: str
    title: str
    model: str | None
    system_prompt: str | None
    created_at: str
    updated_at: str


class UpdateConversationRequest(BaseModel):
    title: str = Field(..., max_length=255)


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str
    provider: str | None
    model: str | None
    provider_meta: dict[str, Any] | None


class ChatSettings(BaseModel):
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    top_p: float | None = Field(None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(None, gt=0)
    stop: list[str] | None = None

    class Config:
        extra = "allow"


class ChatStreamRequest(BaseModel):
    conversation_id: str
    provider_id: str
    model: str
    input: str = Field(..., min_length=1)
    settings: ChatSettings | None = None


class ChatCancelRequest(BaseModel):
    stream_id: str


class ChatRetryRequest(BaseModel):
    conversation_id: str


def get_chat_service(request: Request) -> ChatService:
    service = getattr(request.app.state, "chat_service", None)
    if service:
        return service
    registry = getattr(request.app.state, "provider_registry", None)
    if registry is None:
        registry = ProviderRegistry(get_settings())
        request.app.state.provider_registry = registry
    service = ChatService(registry)
    request.app.state.chat_service = service
    return service


def _conversation_to_response(conversation: Any) -> ConversationResponse:
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        model=conversation.model,
        system_prompt=conversation.system_prompt,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    )


def _message_to_response(message: Any) -> MessageResponse:
    provider_meta = None
    if message.provider_meta:
        try:
            provider_meta = json.loads(message.provider_meta)
        except json.JSONDecodeError:
            provider_meta = None
    return MessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at.isoformat(),
        provider=message.provider,
        model=message.model,
        provider_meta=provider_meta,
    )


@router.post("/conversations")
def create_conversation_route(
    body: CreateConversationRequest,
    auth: RequireAuth,
    db: Session = Depends(get_db),
    _csrf: Any = Depends(ValidateCSRF),
) -> dict[str, Any]:
    user, _ = auth
    conversation = create_conversation(db, user.id, title=body.title)
    return {"conversation": _conversation_to_response(conversation)}


@router.get("/conversations")
def list_conversations_route(
    auth: RequireAuth,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    user, _ = auth
    conversations = list_user_conversations(db, user.id)
    return {
        "conversations": [_conversation_to_response(conv) for conv in conversations]
    }


@router.get("/conversations/{conversation_id}")
def get_conversation_route(
    conversation_id: str,
    auth: RequireAuth,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    user, _ = auth
    conversation = get_user_conversation(db, user.id, conversation_id)
    if not conversation:
        raise NotFoundError("Conversation not found")
    return {"conversation": _conversation_to_response(conversation)}


@router.patch("/conversations/{conversation_id}")
def rename_conversation_route(
    conversation_id: str,
    body: UpdateConversationRequest,
    auth: RequireAuth,
    db: Session = Depends(get_db),
    _csrf: Any = Depends(ValidateCSRF),
) -> dict[str, Any]:
    user, _ = auth
    updated = update_conversation_title(db, user.id, conversation_id, body.title)
    if not updated:
        raise NotFoundError("Conversation not found")
    return {"conversation": _conversation_to_response(updated)}


@router.delete("/conversations/{conversation_id}")
def delete_conversation_route(
    conversation_id: str,
    auth: RequireAuth,
    db: Session = Depends(get_db),
    _csrf: Any = Depends(ValidateCSRF),
) -> dict[str, Any]:
    user, _ = auth
    if not delete_conversation(db, user.id, conversation_id):
        raise NotFoundError("Conversation not found")
    return {"status": "deleted", "conversation_id": conversation_id}


@router.get("/conversations/{conversation_id}/messages")
def list_messages_route(
    conversation_id: str,
    auth: RequireAuth,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    user, _ = auth
    conversation = get_user_conversation(db, user.id, conversation_id)
    if not conversation:
        raise NotFoundError("Conversation not found")
    messages = get_conversation_messages(db, conversation_id)
    return {
        "conversation_id": conversation_id,
        "messages": [_message_to_response(msg) for msg in messages],
    }


@router.post("/chat/stream")
async def chat_stream_route(
    auth: RequireAuth,
    body: ChatStreamRequest = Body(...),
    chat_service: ChatService = Depends(get_chat_service),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    user, _ = auth
    request_id = request_id_ctx.get()
    settings = body.settings.dict(exclude_none=True) if body.settings else {}
    stream = await chat_service.stream_chat(
        db=db,
        user_id=user.id,
        conversation_id=body.conversation_id,
        provider_id=body.provider_id,
        model=body.model,
        user_input=body.input,
        settings=settings,
        request_id=request_id,
    )
    headers = {"X-Request-ID": request_id} if request_id else {}
    return StreamingResponse(stream, media_type="text/event-stream", headers=headers)


@router.post("/chat/cancel")
async def chat_cancel_route(
    auth: RequireAuth,
    body: ChatCancelRequest = Body(...),
    chat_service: ChatService = Depends(get_chat_service),
) -> dict[str, Any]:
    user, _ = auth
    canceled = await chat_service.cancel_stream(body.stream_id, user.id)
    if not canceled:
        raise NotFoundError("Stream not found")
    return {"status": "cancelled", "stream_id": body.stream_id}


@router.post("/chat/retry")
async def chat_retry_route(
    auth: RequireAuth,
    body: ChatRetryRequest = Body(...),
    chat_service: ChatService = Depends(get_chat_service),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    user, _ = auth
    request_id = request_id_ctx.get()
    stream = await chat_service.retry_last_turn(
        db=db,
        user_id=user.id,
        conversation_id=body.conversation_id,
        request_id=request_id,
    )
    headers = {"X-Request-ID": request_id} if request_id else {}
    return StreamingResponse(stream, media_type="text/event-stream", headers=headers)
