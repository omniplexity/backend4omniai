"""Chat service for handling conversations and messages."""

from backend.core.time import utcnow
from typing import AsyncIterator, Dict, List, Optional, Any

from sqlalchemy.orm import Session as DBSession

from backend.core.logging import get_logger
from backend.db.models import Conversation, Message, User
from backend.providers.base import ChatMessage, ChatRequest
from backend.providers.registry import ProviderRegistry
from backend.services.retrieval_service import (
    build_rag_context_message,
    extract_citation_labels,
    retrieve_context,
)

logger = get_logger(__name__)


class ChatService:
    """Service for managing chat conversations."""

    def __init__(self, db: DBSession, registry: ProviderRegistry):
        """Initialize chat service."""
        self.db = db
        self.registry = registry

    def create_conversation(
        self,
        user: User,
        title: str = "New Conversation",
        provider: str = None,
        model: str = None,
    ) -> Conversation:
        """Create a new conversation."""
        conversation = Conversation(
            user_id=user.id,
            title=title,
            provider=provider,
            model=model,
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def get_conversation(
        self,
        conversation_id: str,
        user: User,
    ) -> Optional[Conversation]:
        """Get a conversation by ID."""
        return self.db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        ).first()

    def list_conversations(
        self,
        user: User,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Conversation]:
        """List user's conversations."""
        return self.db.query(Conversation).filter(
            Conversation.user_id == user.id,
        ).order_by(
            Conversation.updated_at.desc()
        ).offset(offset).limit(limit).all()

    def add_message(
        self,
        conversation: Conversation,
        role: str,
        content: str,
        provider: str = None,
        model: str = None,
        tokens_prompt: int = None,
        tokens_completion: int = None,
        message_id: str | None = None,
        parent_message_id: str | None = None,
        revision_of_message_id: str | None = None,
        provider_meta_json: Dict[str, Any] | None = None,
        citations_json: Dict[str, Any] | None = None,
    ) -> Message:
        """Add a message to a conversation."""
        message = Message(
            id=message_id,
            conversation_id=conversation.id,
            role=role,
            content=content,
            provider=provider,
            model=model,
            tokens_prompt=tokens_prompt,
            tokens_completion=tokens_completion,
            parent_message_id=parent_message_id,
            revision_of_message_id=revision_of_message_id,
            provider_meta_json=provider_meta_json,
            citations_json=citations_json,
        )
        self.db.add(message)

        # Update conversation timestamp
        conversation.updated_at = utcnow()

        self.db.commit()
        self.db.refresh(message)
        return message

    def get_messages(
        self,
        conversation: Conversation,
        limit: int = 100,
    ) -> List[Message]:
        """Get messages in a conversation."""
        return self.db.query(Message).filter(
            Message.conversation_id == conversation.id,
        ).order_by(Message.created_at.asc()).limit(limit).all()

    def get_messages_until(
        self,
        conversation: Conversation,
        until_message_id: str | None,
        limit: int = 5000,
    ) -> List[Message]:
        """Get messages up to (and including) a target message."""
        history = self.get_messages(conversation, limit=limit)
        if not until_message_id:
            return history
        cutoff_index = None
        for idx, msg in enumerate(history):
            if msg.id == until_message_id:
                cutoff_index = idx
                break
        if cutoff_index is None:
            return history
        return history[: cutoff_index + 1]

    async def stream_chat_completion(
        self,
        conversation: Conversation,
        user: User,
        user_message: str,
        provider_name: str = None,
        model: str = None,
        assistant_message_id: str | None = None,
        **kwargs,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream a chat completion response.

        Yields:
            Chunks of the response as dictionaries.
        """
        # Get provider
        provider_name = provider_name or self.registry.default_provider
        provider = self.registry.get_provider(provider_name)

        if not provider:
            raise ValueError(f"Provider not found: {provider_name}")

        # Resolve model if not provided
        resolved_model = model or conversation.model
        if not resolved_model:
            try:
                models = await provider.list_models()
                if models:
                    resolved_model = models[0].id
            except Exception:
                pass
        resolved_model = resolved_model or "default"

        # Add user message
        user_entry = self.add_message(conversation, "user", user_message)

        # Build messages for context
        history = self.get_messages(conversation)
        messages: list[ChatMessage] = []

        system_prompt = kwargs.get("system_prompt") or conversation.system_prompt
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))

        sources = await retrieve_context(
            db=self.db,
            user=user,
            registry=self.registry,
            query=user_message,
        )
        ctx_msg = build_rag_context_message(sources)
        if ctx_msg:
            messages.append(ChatMessage(role="system", content=ctx_msg))

        messages.extend([ChatMessage(role=msg.role, content=msg.content) for msg in history])

        # Stream completion
        full_response = ""
        tokens_prompt = None
        tokens_completion = None
        citations_payload = None

        try:
            request = ChatRequest(
                messages=messages,
                model=resolved_model,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens"),
                top_p=kwargs.get("top_p"),
                stop=kwargs.get("stop"),
                stream=True,
            )

            async for chunk in provider.chat_stream(request):
                if chunk.content:
                    full_response += chunk.content

                yield {
                    "content": chunk.content,
                    "finish_reason": chunk.finish_reason,
                    "model": chunk.model or resolved_model,
                }

            # Add assistant response
            if full_response:
                used = extract_citation_labels(full_response)
                citations_payload = {
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
                    "used_labels": used,
                }
                self.add_message(
                    conversation,
                    "assistant",
                    full_response,
                    provider=provider_name,
                    model=resolved_model,
                    tokens_prompt=tokens_prompt,
                    tokens_completion=tokens_completion,
                    message_id=assistant_message_id,
                    parent_message_id=user_entry.id if user_entry else None,
                    citations_json=citations_payload,
                )

        except Exception as e:
            logger.error(f"Chat completion error: {e}")
            raise

    async def chat_completion(
        self,
        conversation: Conversation,
        user: User,
        user_message: str,
        provider_name: str = None,
        model: str = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Non-streaming chat completion."""
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

        user_entry = self.add_message(conversation, "user", user_message)

        history = self.get_messages(conversation)
        messages: list[ChatMessage] = []
        system_prompt = kwargs.get("system_prompt") or conversation.system_prompt
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))

        sources = await retrieve_context(
            db=self.db,
            user=user,
            registry=self.registry,
            query=user_message,
        )
        ctx_msg = build_rag_context_message(sources)
        if ctx_msg:
            messages.append(ChatMessage(role="system", content=ctx_msg))

        messages.extend([ChatMessage(role=msg.role, content=msg.content) for msg in history])

        request = ChatRequest(
            messages=messages,
            model=resolved_model,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens"),
            top_p=kwargs.get("top_p"),
            stop=kwargs.get("stop"),
            stream=False,
        )

        response = await provider.chat_once(request)

        used = extract_citation_labels(response.content or "")
        citations_payload = {
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
            "used_labels": used,
        }
        self.add_message(
            conversation,
            "assistant",
            response.content,
            provider=provider_name,
            model=response.model or resolved_model,
            tokens_prompt=response.prompt_tokens,
            tokens_completion=response.completion_tokens,
            parent_message_id=user_entry.id if user_entry else None,
            citations_json=citations_payload,
        )

        return {
            "content": response.content,
            "finish_reason": response.finish_reason,
            "model": response.model,
            "usage": {
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
            },
        }

    def delete_conversation(self, conversation: Conversation) -> None:
        """Delete a conversation and its messages."""
        self.db.delete(conversation)
        self.db.commit()

    def update_conversation_title(
        self,
        conversation: Conversation,
        title: str,
    ) -> Conversation:
        """Update conversation title."""
        conversation.title = title
        self.db.commit()
        self.db.refresh(conversation)
        return conversation
