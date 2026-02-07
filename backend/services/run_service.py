"""Run execution for v1 chat endpoints."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session as DBSession

from backend.core.logging import get_logger
from backend.db.database import get_session_local
from backend.db.models import ChatRun, ChatRunEvent, Conversation, Message, User, generate_id
from backend.providers.base import ChatMessage, ChatRequest
from backend.providers.registry import ProviderRegistry
from backend.services.chat_service import ChatService
from backend.services.retrieval_service import (
    build_rag_context_message,
    extract_citation_labels,
    retrieve_context,
)

logger = get_logger(__name__)


class RunService:
    def __init__(self, registry: ProviderRegistry):
        self.registry = registry

    def start_run(
        self,
        db: DBSession,
        user: User,
        conversation: Conversation,
        input_text: str,
        provider_name: Optional[str],
        model: Optional[str],
        settings: Dict[str, Any] | None = None,
        retry_from_message_id: Optional[str] = None,
    ) -> ChatRun:
        run = ChatRun(
            user_id=user.id,
            conversation_id=conversation.id,
            provider=provider_name or conversation.provider,
            model=model or conversation.model,
            settings_json=settings or {},
            status="running",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        asyncio.create_task(
            execute_run(
                run_id=run.id,
                user_id=user.id,
                conversation_id=conversation.id,
                input_text=input_text,
                provider_name=provider_name,
                model=model,
                settings=settings or {},
                retry_from_message_id=retry_from_message_id,
                registry=self.registry,
            )
        )
        return run

    async def chat_once(
        self,
        db: DBSession,
        conversation: Conversation,
        user: User,
        input_text: str,
        provider_name: Optional[str],
        model: Optional[str],
        settings: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        settings = settings or {}
        provider_name = provider_name or self.registry.default_provider
        provider = self.registry.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Provider not found: {provider_name}")

        resolved_model = model or conversation.model
        if not resolved_model:
            try:
                models = await provider.list_models()
                if models:
                    resolved_model = models[0].id
            except Exception:
                pass
        resolved_model = resolved_model or "default"

        service = ChatService(db, self.registry)
        user_message = service.add_message(conversation, "user", input_text, provider=provider_name, model=resolved_model)

        history = service.get_messages_until(conversation, user_message.id)
        system_prompt = settings.get("system_prompt") or conversation.system_prompt
        messages = []
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        sources = await retrieve_context(db=db, user=user, registry=self.registry, query=input_text)
        ctx_msg = build_rag_context_message(sources)
        if ctx_msg:
            messages.append(ChatMessage(role="system", content=ctx_msg))
        messages.extend([ChatMessage(role=msg.role, content=msg.content) for msg in history])

        request = ChatRequest(
            messages=messages,
            model=resolved_model,
            temperature=settings.get("temperature", 0.7),
            max_tokens=settings.get("max_tokens"),
            top_p=settings.get("top_p"),
            stop=settings.get("stop"),
            stream=False,
        )
        started = time.monotonic()
        response = await provider.chat_once(request)
        total_ms = int((time.monotonic() - started) * 1000)

        provider_meta = {
            "request_id": str(uuid.uuid4()),
            "provider": provider_name,
            "model": response.model or resolved_model,
            "timing_ms": {"ttft": None, "total": total_ms},
            "tokens": {
                "prompt": response.prompt_tokens,
                "completion": response.completion_tokens,
                "total": response.total_tokens,
            },
            "tool_calls": [],
            "error": None,
        }

        assistant_message = service.add_message(
            conversation,
            "assistant",
            response.content,
            provider=provider_name,
            model=response.model or resolved_model,
            tokens_prompt=response.prompt_tokens,
            tokens_completion=response.completion_tokens,
            parent_message_id=user_message.id,
            provider_meta_json=provider_meta,
            citations_json={
                "sources": [
                    {
                        "label": s.label,
                        "type": s.source_type,
                        "score": s.score,
                        "title": s.title,
                        "snippet": s.snippet,
                        "meta": s.meta,
                    }
                    for s in sources
                ],
                "used_labels": extract_citation_labels(response.content or ""),
            },
        )

        return {
            "message": assistant_message,
            "provider_meta": provider_meta,
        }


async def execute_run(
    run_id: str,
    user_id: str,
    conversation_id: str,
    input_text: str,
    provider_name: Optional[str],
    model: Optional[str],
    settings: Dict[str, Any],
    retry_from_message_id: Optional[str],
    registry: ProviderRegistry,
) -> None:
    SessionLocal = get_session_local()
    db = SessionLocal()
    logger.info(f"execute_run started", data={"run_id": run_id, "provider": provider_name, "model": model})
    try:
        run = db.query(ChatRun).filter(ChatRun.id == run_id).first()
        user = db.query(User).filter(User.id == user_id).first()
        conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not run or not user or not conversation:
            logger.error(f"execute_run: missing resources", data={"run": bool(run), "user": bool(user), "conversation": bool(conversation)})
            return

        service = ChatService(db, registry)

        provider_name = provider_name or registry.default_provider
        provider = registry.get_provider(provider_name)
        logger.info(f"execute_run: using provider", data={"provider_name": provider_name, "provider_found": bool(provider)})
        if not provider:
            run.status = "error"
            run.error_code = "E4040"
            run.error_message = "Provider not found"
            db.commit()
            return

        resolved_model = model or conversation.model
        if not resolved_model:
            try:
                models = await provider.list_models()
                if models:
                    resolved_model = models[0].id
            except Exception:
                pass
        resolved_model = resolved_model or "default"

        assistant_message_id = generate_id()
        request_id = str(uuid.uuid4())
        started_monotonic = time.monotonic()
        ttft_ms: Optional[int] = None
        full_response = ""
        last_finish_reason = None

        def persist_event(event_type: str, payload: Dict[str, Any]) -> None:
            seq = db.query(ChatRunEvent).filter(ChatRunEvent.run_id == run.id).count() + 1
            enriched = dict(payload or {})
            enriched["emitted_at"] = datetime.utcnow().isoformat()
            db.add(ChatRunEvent(run_id=run.id, seq=seq, type=event_type, payload_json=enriched))
            db.commit()

        def load_run_status() -> str:
            refreshed = db.query(ChatRun).filter(ChatRun.id == run.id).first()
            return refreshed.status if refreshed else "error"

        user_message_entry: Optional[Message] = None
        revision_of_message_id: Optional[str] = None

        if retry_from_message_id:
            history = service.get_messages_until(conversation, retry_from_message_id)
            target = next((msg for msg in history if msg.id == retry_from_message_id), None)
            if target and target.role == "assistant":
                revision_of_message_id = target.id
            # find the last user message in history
            for msg in reversed(history):
                if msg.role == "user":
                    user_message_entry = msg
                    break
            if not user_message_entry:
                raise RuntimeError("No user message available to retry")
            history_messages = history
        else:
            user_message_entry = service.add_message(conversation, "user", input_text, provider=provider_name, model=resolved_model)
            history_messages = service.get_messages_until(conversation, user_message_entry.id)

        system_prompt = settings.get("system_prompt") or conversation.system_prompt
        messages = []
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        sources = await retrieve_context(db=db, user=user, registry=registry, query=input_text or (user_message_entry.content if user_message_entry else ""))
        ctx_msg = build_rag_context_message(sources)
        if ctx_msg:
            messages.append(ChatMessage(role="system", content=ctx_msg))
        messages.extend([ChatMessage(role=msg.role, content=msg.content) for msg in history_messages])

        persist_event(
            "run.start",
            {
                "run_id": run.id,
                "conversation_id": conversation.id,
                "provider": provider_name,
                "model": resolved_model,
                "settings": settings,
                "started_at": run.created_at.isoformat(),
            },
        )
        persist_event(
            "run.status",
            {
                "run_id": run.id,
                "status": "running",
                "started_at": run.created_at.isoformat(),
                "updated_at": run.updated_at.isoformat(),
                "provider": provider_name,
                "model": resolved_model,
            },
        )

        try:
            request = ChatRequest(
                messages=messages,
                model=resolved_model,
                temperature=settings.get("temperature", 0.7),
                max_tokens=settings.get("max_tokens"),
                top_p=settings.get("top_p"),
                stop=settings.get("stop"),
                stream=True,
            )
            logger.info(f"execute_run: starting chat_stream", data={"model": resolved_model, "message_count": len(messages)})
            chunk_count = 0
            
            async for chunk in provider.chat_stream(request):
                chunk_count += 1
                if load_run_status() == "cancelled":
                    persist_event(
                        "run.status",
                        {
                            "run_id": run.id,
                            "status": "cancelled",
                            "updated_at": datetime.utcnow().isoformat(),
                            "provider": provider_name,
                            "model": resolved_model,
                            "cancel_reason": "user_cancel",
                        },
                    )
                    return

                if chunk.content:
                    if ttft_ms is None:
                        ttft_ms = int((time.monotonic() - started_monotonic) * 1000)
                    full_response += chunk.content
                    persist_event(
                        "message.delta",
                        {
                            "run_id": run.id,
                            "message_id": assistant_message_id,
                            "role": "assistant",
                            "delta": chunk.content,
                        },
                    )
                if chunk.finish_reason:
                    last_finish_reason = chunk.finish_reason

            run.status = "completed"
            db.commit()
            total_ms = int((time.monotonic() - started_monotonic) * 1000)
            logger.info(f"execute_run: completed", data={"run_id": run_id, "chunks": chunk_count, "total_ms": total_ms})

            provider_meta = {
                "request_id": request_id,
                "provider": provider_name,
                "model": resolved_model,
                "timing_ms": {"ttft": ttft_ms, "total": total_ms},
                "tokens": {"prompt": None, "completion": None, "total": None},
                "tool_calls": [],
                "error": None,
            }

            assistant_message = service.add_message(
                conversation,
                "assistant",
                full_response,
                provider=provider_name,
                model=resolved_model,
                parent_message_id=user_message_entry.id if user_message_entry else None,
                revision_of_message_id=revision_of_message_id,
                message_id=assistant_message_id,
                provider_meta_json=provider_meta,
                citations_json={
                    "sources": [
                        {
                            "label": s.label,
                            "type": s.source_type,
                            "score": s.score,
                            "title": s.title,
                            "snippet": s.snippet,
                            "meta": s.meta,
                        }
                        for s in sources
                    ],
                    "used_labels": extract_citation_labels(full_response or ""),
                },
            )

            persist_event(
                "message.final",
                {
                    "run_id": run.id,
                    "message_id": assistant_message.id,
                    "role": "assistant",
                    "content": full_response,
                    "finish_reason": last_finish_reason,
                    "provider": provider_name,
                    "model": resolved_model,
                    "created_at": datetime.utcnow().isoformat(),
                },
            )
            persist_event(
                "receipt",
                {
                    "message_id": assistant_message.id,
                    "provider_meta": provider_meta,
                },
            )
            persist_event(
                "run.metrics",
                {
                    "run_id": run.id,
                    "latency_ms": {"total": total_ms, "ttft": ttft_ms},
                },
            )
            persist_event(
                "run.status",
                {
                    "run_id": run.id,
                    "status": "completed",
                    "updated_at": datetime.utcnow().isoformat(),
                    "completed_at": datetime.utcnow().isoformat(),
                    "provider": provider_name,
                    "model": resolved_model,
                    "latency_ms": {"total": total_ms, "ttft": ttft_ms},
                },
            )
        except Exception as exc:
            run.status = "error"
            run.error_code = "E5000"
            run.error_message = str(exc)
            db.commit()
            persist_event(
                "error",
                {
                    "run_id": run.id,
                    "code": run.error_code,
                    "message": run.error_message,
                },
            )
            persist_event(
                "run.status",
                {
                    "run_id": run.id,
                    "status": "error",
                    "updated_at": datetime.utcnow().isoformat(),
                    "provider": provider_name,
                    "model": resolved_model,
                    "error_code": run.error_code,
                    "error_message": run.error_message,
                },
            )
    except Exception as exc:
        logger.error("Run execution failed", data={"error": str(exc)})
    finally:
        db.close()
