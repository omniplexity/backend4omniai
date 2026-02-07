"""v1 chat endpoints.

These endpoints use the Chat Agent for chat operations.
"""

import json
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_current_user
from backend.config import get_settings
from backend.core.logging import get_logger
from backend.db import get_db
from backend.db.models import ChatRun, ChatRunEvent, Conversation, User
from backend.agents.chat import ChatAgent
from backend.agents.provider import ProviderAgent
from backend.agents.conversation import ConversationAgent

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["v1-chat"])


class ChatRequest(BaseModel):
    """Chat request."""
    conversation_id: str
    input: Optional[str] = Field(default=None)
    provider: Optional[str] = None
    model: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    stream: bool = False
    retry_from_message_id: Optional[str] = None


class ChatRetryRequest(BaseModel):
    """Retry chat request."""
    conversation_id: str
    message_id: str
    provider: Optional[str] = None
    model: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class ChatCancelRequest(BaseModel):
    """Cancel chat request."""
    run_id: str


def _format_sse_event(seq: int, event_type: str, payload: Dict[str, Any]) -> str:
    """Format an SSE event."""
    return f"id: {seq}\nevent: {event_type}\ndata: {json.dumps(payload)}\n\n"


def _create_chat_agent(db: DBSession, request: Request) -> ChatAgent:
    """Create a Chat Agent instance."""
    registry = getattr(request.app.state, "provider_registry", None)
    provider_agent = ProviderAgent(get_settings(), registry)
    conversation_agent = ConversationAgent(db)
    return ChatAgent(db, provider_agent, conversation_agent)


@router.post("")
async def create_chat_run(
    body: ChatRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new chat run (streaming or non-streaming)."""
    registry = getattr(request.app.state, "provider_registry", None)
    if not registry:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No providers available")

    conversation = db.query(Conversation).filter(
        Conversation.id == body.conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    chat_agent = _create_chat_agent(db, request)

    if body.stream:
        if not body.input and not body.retry_from_message_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Input required")
        
        run = chat_agent.create_run(
            conversation=conversation,
            user=current_user,
            input_text=body.input or "",
            provider_name=body.provider,
            model=body.model,
            retry_from_message_id=body.retry_from_message_id,
        )
        return {"run_id": run.id, "status": run.status}

    if not body.input:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Input required")

    try:
        result = await chat_agent.send_message(
            conversation=conversation,
            user=current_user,
            content=body.input,
            provider_name=body.provider,
            model=body.model,
            stream=False,
        )
    except Exception as exc:
        logger.error("Chat completion failed", data={"error": str(exc)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return result


@router.post("/retry")
async def retry_chat_run(
    body: ChatRetryRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retry a message in a conversation."""
    registry = getattr(request.app.state, "provider_registry", None)
    if not registry:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No providers available")

    conversation = db.query(Conversation).filter(
        Conversation.id == body.conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    chat_agent = _create_chat_agent(db, request)

    run = chat_agent.retry_message(
        conversation=conversation,
        user=current_user,
        message_id=body.message_id,
        provider_name=body.provider,
        model=body.model,
    )
    return {"run_id": run.id, "status": run.status}


@router.post("/cancel")
async def cancel_chat_run(
    body: ChatCancelRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a running chat."""
    chat_agent = _create_chat_agent(db, request := Request)

    run = chat_agent.get_run(body.run_id, current_user)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    chat_agent.cancel_run(run)
    return {"status": "cancelled", "run_id": run.id}


@router.get("/stream")
async def stream_chat_run(
    run_id: str,
    request: Request,
    after: Optional[int] = None,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream events from a chat run."""
    run = db.query(ChatRun).filter(ChatRun.id == run_id, ChatRun.user_id == current_user.id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    last_event_id = after
    if last_event_id is None:
        header = request.headers.get("Last-Event-ID")
        if header and header.isdigit():
            last_event_id = int(header)
        else:
            last_event_id = 0

    settings = get_settings()
    ping_interval = settings.sse_ping_interval_seconds

    async def event_stream():
        nonlocal last_event_id
        last_ping = time.monotonic()
        while True:
            events = (
                db.query(ChatRunEvent)
                .filter(ChatRunEvent.run_id == run.id, ChatRunEvent.seq > last_event_id)
                .order_by(ChatRunEvent.seq.asc())
                .limit(200)
                .all()
            )
            for evt in events:
                last_event_id = evt.seq
                payload = evt.payload_json or {}
                yield _format_sse_event(evt.seq, evt.type, payload)

            if await request.is_disconnected():
                break

            now = time.monotonic()
            if ping_interval and (now - last_ping) >= ping_interval:
                last_ping = now
                yield ": ping\n\n"

            refreshed = db.query(ChatRun).filter(ChatRun.id == run.id).first()
            if refreshed and refreshed.status in {"completed", "cancelled", "error"} and not events:
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# Import asyncio at module level for the streaming function
import asyncio
