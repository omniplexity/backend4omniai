"""Chat API endpoints."""

import asyncio
import json
import time
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import text

from backend.auth.dependencies import get_current_user
from backend.core.logging import get_logger
from backend.db import get_db
from backend.db.models import User, ChatRun, ChatRunEvent, Conversation, Message, generate_id
from backend.services.chat_service import ChatService

logger = get_logger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


class MessageModel(BaseModel):
    """Message model."""

    id: str
    role: str
    content: str
    provider: Optional[str]
    model: Optional[str]
    tokens_prompt: Optional[int]
    tokens_completion: Optional[int]
    parent_message_id: Optional[str] = None
    revision_of_message_id: Optional[str] = None
    content_parts_json: Optional[Dict[str, Any]] = None
    citations_json: Optional[Dict[str, Any]] = None
    tool_events_json: Optional[Dict[str, Any]] = None
    provider_meta_json: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class ConversationModel(BaseModel):
    """Conversation model."""

    id: str
    title: str
    provider: Optional[str]
    model: Optional[str]
    project_id: Optional[str] = None
    parent_conversation_id: Optional[str] = None
    branched_from_message_id: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class CreateConversationRequest(BaseModel):
    """Create conversation request."""

    title: str = Field(default="New Conversation")
    provider: Optional[str] = None
    model: Optional[str] = None
    project_id: Optional[str] = None


class SendMessageRequest(BaseModel):
    """Send message request."""

    content: str = Field(min_length=1)
    provider: Optional[str] = None
    model: Optional[str] = None
    stream: bool = True
    settings: Optional[Dict[str, Any]] = None


class UpdateConversationRequest(BaseModel):
    """Update conversation request."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    project_id: Optional[str] = None


class BranchConversationRequest(BaseModel):
    from_message_id: str
    title: Optional[str] = None


class RunStreamRequest(BaseModel):
    input: str = Field(min_length=1)
    provider: Optional[str] = None
    model: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class RunModel(BaseModel):
    id: str
    conversation_id: str
    provider: Optional[str]
    model: Optional[str]
    status: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


@router.get("/conversations", response_model=List[ConversationModel])
async def list_conversations(
    limit: int = 50,
    offset: int = 0,
    request: Request = None,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List user's conversations."""
    registry = getattr(request.app.state, "provider_registry", None)
    service = ChatService(db, registry)

    conversations = service.list_conversations(current_user, limit, offset)

    return [
        ConversationModel(
            id=c.id,
            title=c.title,
            provider=c.provider,
            model=c.model,
            project_id=c.project_id,
            parent_conversation_id=c.parent_conversation_id,
            branched_from_message_id=c.branched_from_message_id,
            created_at=c.created_at.isoformat(),
            updated_at=c.updated_at.isoformat(),
        )
        for c in conversations
    ]


@router.post("/conversations", response_model=ConversationModel)
async def create_conversation(
    body: CreateConversationRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new conversation."""
    registry = getattr(request.app.state, "provider_registry", None)
    service = ChatService(db, registry)

    conversation = service.create_conversation(
        current_user,
        title=body.title,
        provider=body.provider,
        model=body.model,
    )
    if body.project_id is not None:
        conversation.project_id = body.project_id
        db.commit()
        db.refresh(conversation)

    return ConversationModel(
        id=conversation.id,
        title=conversation.title,
        provider=conversation.provider,
        model=conversation.model,
        project_id=conversation.project_id,
        parent_conversation_id=conversation.parent_conversation_id,
        branched_from_message_id=conversation.branched_from_message_id,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationModel)
async def get_conversation(
    conversation_id: str,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a conversation by ID."""
    registry = getattr(request.app.state, "provider_registry", None)
    service = ChatService(db, registry)

    conversation = service.get_conversation(conversation_id, current_user)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return ConversationModel(
        id=conversation.id,
        title=conversation.title,
        provider=conversation.provider,
        model=conversation.model,
        project_id=conversation.project_id,
        parent_conversation_id=conversation.parent_conversation_id,
        branched_from_message_id=conversation.branched_from_message_id,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationModel)
async def update_conversation(
    conversation_id: str,
    body: UpdateConversationRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a conversation's title."""
    registry = getattr(request.app.state, "provider_registry", None)
    service = ChatService(db, registry)

    conversation = service.get_conversation(conversation_id, current_user)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if body.title:
        conversation = service.update_conversation_title(conversation, body.title)
    if body.project_id is not None:
        conversation.project_id = body.project_id
        db.commit()
        db.refresh(conversation)

    return ConversationModel(
        id=conversation.id,
        title=conversation.title,
        provider=conversation.provider,
        model=conversation.model,
        project_id=conversation.project_id,
        parent_conversation_id=conversation.parent_conversation_id,
        branched_from_message_id=conversation.branched_from_message_id,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a conversation."""
    registry = getattr(request.app.state, "provider_registry", None)
    service = ChatService(db, registry)

    conversation = service.get_conversation(conversation_id, current_user)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    service.delete_conversation(conversation)

    return {"message": "Conversation deleted"}


@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageModel])
async def get_messages(
    conversation_id: str,
    limit: int = 100,
    request: Request = None,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get messages in a conversation."""
    registry = getattr(request.app.state, "provider_registry", None)
    service = ChatService(db, registry)

    conversation = service.get_conversation(conversation_id, current_user)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    messages = service.get_messages(conversation, limit)

    return [MessageModel.model_validate(m) for m in messages]


@router.post("/conversations/{conversation_id}/branch", response_model=ConversationModel)
async def branch_conversation(
    conversation_id: str,
    body: BranchConversationRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    registry = getattr(request.app.state, "provider_registry", None)
    service = ChatService(db, registry)

    conversation = service.get_conversation(conversation_id, current_user)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    source_messages = service.get_messages(conversation, limit=5000)
    cutoff_index = None
    for idx, msg in enumerate(source_messages):
        if msg.id == body.from_message_id:
            cutoff_index = idx
            break
    if cutoff_index is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    new_title = body.title or f"{conversation.title} (branch)"
    new_convo = service.create_conversation(
        current_user,
        title=new_title,
        provider=conversation.provider,
        model=conversation.model,
    )
    new_convo.project_id = conversation.project_id
    new_convo.parent_conversation_id = conversation.id
    new_convo.branched_from_message_id = body.from_message_id
    db.commit()
    db.refresh(new_convo)

    for msg in source_messages[: cutoff_index + 1]:
        clone = Message(
            conversation_id=new_convo.id,
            role=msg.role,
            content=msg.content,
            tokens_prompt=msg.tokens_prompt,
            tokens_completion=msg.tokens_completion,
            provider=msg.provider,
            model=msg.model,
            created_at=msg.created_at,
        )
        db.add(clone)
    db.commit()

    return ConversationModel(
        id=new_convo.id,
        title=new_convo.title,
        provider=new_convo.provider,
        model=new_convo.model,
        project_id=new_convo.project_id,
        parent_conversation_id=new_convo.parent_conversation_id,
        branched_from_message_id=new_convo.branched_from_message_id,
        created_at=new_convo.created_at.isoformat(),
        updated_at=new_convo.updated_at.isoformat(),
    )


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a message and get a response."""
    registry = getattr(request.app.state, "provider_registry", None)

    if not registry:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No providers available",
        )

    service = ChatService(db, registry)

    conversation = service.get_conversation(conversation_id, current_user)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if body.stream:
        async def stream_response():
            """Stream the chat response as SSE."""
            import json
            import time

            settings = None
            try:
                from backend.config import get_settings
                settings = get_settings()
            except Exception:
                settings = None

            ping_interval = getattr(settings, "sse_ping_interval_seconds", 0) if settings else 0
            last_ping = time.monotonic()

            try:
                async for chunk in service.stream_chat_completion(
                    conversation,
                    current_user,
                    body.content,
                    provider_name=body.provider,
                    model=body.model,
                    **(body.settings or {}),
                ):
                    if await request.is_disconnected():
                        break

                    now = time.monotonic()
                    if ping_interval and (now - last_ping) >= ping_interval:
                        last_ping = now
                        yield ": ping\n\n"

                    yield f"data: {json.dumps(chunk)}\n\n"

                yield "data: [DONE]\n\n"

            except Exception as e:
                logger.error(f"Stream error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            stream_response(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    else:
        # Non-streaming response
        response = await service.chat_completion(
            conversation,
            current_user,
            body.content,
            provider_name=body.provider,
            model=body.model,
            **(body.settings or {}),
        )

        return {"content": response["content"]}


@router.get("/conversations/{conversation_id}/runs", response_model=List[RunModel])
async def list_runs(
    conversation_id: str,
    limit: int = 50,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    runs = (
        db.query(ChatRun)
        .filter(ChatRun.user_id == current_user.id, ChatRun.conversation_id == conversation_id)
        .order_by(ChatRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        RunModel(
            id=r.id,
            conversation_id=r.conversation_id,
            provider=r.provider,
            model=r.model,
            status=r.status,
            created_at=r.created_at.isoformat(),
            updated_at=r.updated_at.isoformat(),
        )
        for r in runs
    ]


def _format_sse_event(seq: int, event_type: str, payload: Dict[str, Any]) -> str:
    return f"id: {seq}\nevent: {event_type}\ndata: {json.dumps(payload)}\n\n"


@router.post("/conversations/{conversation_id}/runs/stream")
async def stream_run(
    conversation_id: str,
    body: RunStreamRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    registry = getattr(request.app.state, "provider_registry", None)
    if not registry:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No providers available")
    service = ChatService(db, registry)
    conversation = service.get_conversation(conversation_id, current_user)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    run = ChatRun(
        user_id=current_user.id,
        conversation_id=conversation.id,
        provider=body.provider or conversation.provider,
        model=body.model or conversation.model,
        settings_json=body.settings or {},
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    async def event_stream():
        seq = 0
        settings = None
        try:
            from backend.config import get_settings
            settings = get_settings()
        except Exception:
            settings = None

        ping_interval = getattr(settings, "sse_ping_interval_seconds", 0) if settings else 0
        last_ping = time.monotonic()

        def persist_event(event_type: str, payload: Dict[str, Any]) -> str:
            nonlocal seq
            seq += 1
            enriched = dict(payload or {})
            enriched["emitted_at"] = datetime.utcnow().isoformat()
            db.add(ChatRunEvent(run_id=run.id, seq=seq, type=event_type, payload_json=enriched))
            db.commit()
            return _format_sse_event(seq, event_type, enriched)

        def load_run_status() -> str:
            refreshed = db.query(ChatRun).filter(ChatRun.id == run.id).first()
            return refreshed.status if refreshed else "error"

        assistant_message_id = generate_id()
        full_response = ""
        last_finish_reason = None
        last_model = run.model
        started_monotonic = time.monotonic()
        ttft_ms: Optional[int] = None

        yield persist_event(
            "run.start",
            {
                "run_id": run.id,
                "conversation_id": conversation.id,
                "provider": run.provider,
                "model": run.model,
                "settings": run.settings_json,
                "started_at": run.created_at.isoformat(),
            },
        )
        yield persist_event(
            "run.status",
            {
                "run_id": run.id,
                "status": "running",
                "started_at": run.created_at.isoformat(),
                "updated_at": run.updated_at.isoformat(),
                "provider": run.provider,
                "model": run.model,
            },
        )

        try:
            async for chunk in service.stream_chat_completion(
                conversation,
                current_user,
                body.input,
                provider_name=body.provider,
                model=body.model,
                assistant_message_id=assistant_message_id,
                **(body.settings or {}),
            ):
                if await request.is_disconnected():
                    break

                if load_run_status() == "cancelled":
                    yield persist_event(
                        "run.status",
                        {
                            "run_id": run.id,
                            "status": "cancelled",
                            "started_at": run.created_at.isoformat(),
                            "updated_at": datetime.utcnow().isoformat(),
                            "provider": run.provider,
                            "model": last_model,
                            "cancel_reason": "user_cancel",
                        },
                    )
                    return

                now = time.monotonic()
                if ping_interval and (now - last_ping) >= ping_interval:
                    last_ping = now
                    yield ": ping\n\n"

                if chunk.get("content"):
                    if ttft_ms is None:
                        ttft_ms = int((time.monotonic() - started_monotonic) * 1000)
                    full_response += chunk["content"]
                    yield persist_event(
                        "message.delta",
                        {
                            "run_id": run.id,
                            "message_id": assistant_message_id,
                            "role": "assistant",
                            "delta": chunk["content"],
                        },
                    )
                if chunk.get("finish_reason"):
                    last_finish_reason = chunk["finish_reason"]
                if chunk.get("model"):
                    last_model = chunk["model"]

            run.status = "completed"
            db.commit()
            total_ms = int((time.monotonic() - started_monotonic) * 1000)
            yield persist_event(
                "message.final",
                {
                    "run_id": run.id,
                    "message_id": assistant_message_id,
                    "role": "assistant",
                    "content": full_response,
                    "finish_reason": last_finish_reason,
                    "provider": run.provider,
                    "model": last_model,
                    "created_at": datetime.utcnow().isoformat(),
                },
            )
            yield persist_event(
                "run.metrics",
                {
                    "run_id": run.id,
                    "latency_ms": {"total": total_ms, "ttft": ttft_ms},
                },
            )
            yield persist_event(
                "run.status",
                {
                    "run_id": run.id,
                    "status": "completed",
                    "started_at": run.created_at.isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    "completed_at": datetime.utcnow().isoformat(),
                    "provider": run.provider,
                    "model": last_model,
                    "latency_ms": {"total": total_ms, "ttft": ttft_ms},
                },
            )
        except Exception as exc:
            run.status = "error"
            run.error_code = "E5000"
            run.error_message = str(exc)
            db.commit()
            yield persist_event(
                "error",
                {
                    "run_id": run.id,
                    "code": "E5000",
                    "message": str(exc),
                },
            )
            yield persist_event(
                "run.status",
                {
                    "run_id": run.id,
                    "status": "error",
                    "started_at": run.created_at.isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    "provider": run.provider,
                    "model": last_model,
                    "error_code": run.error_code,
                    "error_message": run.error_message,
                },
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/runs/{run_id}/stream")
async def resume_run_stream(
    run_id: str,
    request: Request,
    after: Optional[int] = None,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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

    async def event_stream():
        nonlocal last_event_id
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
                yield _format_sse_event(evt.seq, evt.type, evt.payload_json or {})

            if await request.is_disconnected():
                break

            refreshed = db.query(ChatRun).filter(ChatRun.id == run.id).first()
            if refreshed and refreshed.status in {"completed", "cancelled", "error"} and not events:
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = db.query(ChatRun).filter(ChatRun.id == run_id, ChatRun.user_id == current_user.id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    run.status = "cancelled"
    run.cancelled_at = datetime.utcnow()
    db.commit()
    return {"status": "cancelled", "run_id": run.id}


@router.get("/runs/{run_id}/export")
async def export_run(
    run_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = db.query(ChatRun).filter(ChatRun.id == run_id, ChatRun.user_id == current_user.id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    events = (
        db.query(ChatRunEvent)
        .filter(ChatRunEvent.run_id == run.id)
        .order_by(ChatRunEvent.seq.asc())
        .all()
    )
    return {
        "run": {
            "id": run.id,
            "conversation_id": run.conversation_id,
            "provider": run.provider,
            "model": run.model,
            "status": run.status,
            "settings": run.settings_json,
            "created_at": run.created_at.isoformat(),
            "updated_at": run.updated_at.isoformat(),
            "cancelled_at": run.cancelled_at.isoformat() if run.cancelled_at else None,
            "error_code": run.error_code,
            "error_message": run.error_message,
        },
        "events": [
            {"seq": e.seq, "type": e.type, "payload": e.payload_json, "created_at": e.created_at.isoformat()}
            for e in events
        ],
    }


@router.get("/search")
async def search_chat(
    q: str,
    project_id: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    limit: int = 20,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not q:
        return {"conversations": [], "messages": []}

    dialect = db.bind.dialect.name if db.bind else "sqlite"
    if dialect == "sqlite":
        conv_sql = """
        SELECT c.id, c.title
        FROM chat_conversations_fts f
        JOIN conversations c ON c.id = f.conversation_id
        WHERE f MATCH :query AND c.user_id = :user_id
        """
        msg_sql = """
        SELECT m.id as message_id, m.conversation_id,
               snippet(chat_messages_fts, 2, '[', ']', '…', 20) as snippet
        FROM chat_messages_fts f
        JOIN messages m ON m.id = f.message_id
        JOIN conversations c ON c.id = m.conversation_id
        WHERE f MATCH :query AND c.user_id = :user_id
        """
        params = {"query": q, "user_id": current_user.id}
        if project_id:
            conv_sql += " AND c.project_id = :project_id"
            msg_sql += " AND c.project_id = :project_id"
            params["project_id"] = project_id
        if provider:
            conv_sql += " AND c.provider = :provider"
            msg_sql += " AND c.provider = :provider"
            params["provider"] = provider
        if model:
            conv_sql += " AND c.model = :model"
            msg_sql += " AND c.model = :model"
            params["model"] = model
        conv_sql += " LIMIT :limit"
        msg_sql += " LIMIT :limit"
        params["limit"] = limit

        conversations = db.execute(text(conv_sql), params).fetchall()
        messages = db.execute(text(msg_sql), params).fetchall()
        return {
            "conversations": [{"id": row[0], "title": row[1]} for row in conversations],
            "messages": [
                {"id": row[0], "conversation_id": row[1], "snippet": row[2]} for row in messages
            ],
        }

    conv_query = db.query(Conversation).filter(Conversation.user_id == current_user.id)
    msg_query = db.query(Message).join(Conversation).filter(Conversation.user_id == current_user.id)
    if project_id:
        conv_query = conv_query.filter(Conversation.project_id == project_id)
        msg_query = msg_query.filter(Conversation.project_id == project_id)
    if provider:
        conv_query = conv_query.filter(Conversation.provider == provider)
        msg_query = msg_query.filter(Conversation.provider == provider)
    if model:
        conv_query = conv_query.filter(Conversation.model == model)
        msg_query = msg_query.filter(Conversation.model == model)

    conv_hits = (
        conv_query.filter(Conversation.title.ilike(f"%{q}%"))
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .all()
    )
    msg_hits = (
        msg_query.filter(Message.content.ilike(f"%{q}%"))
        .order_by(Message.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "conversations": [{"id": c.id, "title": c.title} for c in conv_hits],
        "messages": [
            {"id": m.id, "conversation_id": m.conversation_id, "snippet": (m.content or "")[:160]}
            for m in msg_hits
        ],
    }
