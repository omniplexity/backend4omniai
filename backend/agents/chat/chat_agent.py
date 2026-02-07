"""Chat Agent.

Handles chat operations, streaming responses, and message flow.
Orchestrates between Provider Agent and Conversation Agent.
"""

import json
import time
from typing import AsyncGenerator, Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session as DBSession

from backend.db.models import User, Conversation, Message, ChatRun, ChatRunEvent, generate_id
from backend.agents.conversation import ConversationAgent
from backend.agents.provider import ProviderAgent, ChatMessage, ChatRequest
from backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ChatSettings:
    """Chat settings for a request."""
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None


@dataclass
class RunInfo:
    """Chat run information."""
    id: str
    conversation_id: str
    provider: Optional[str]
    model: Optional[str]
    status: str
    created_at: datetime


@dataclass
class StreamEvent:
    """Streaming event."""
    type: str
    payload: Dict[str, Any]


class ChatAgent:
    """Agent for handling chat operations."""

    def __init__(
        self, 
        db: DBSession,
        provider_agent: ProviderAgent,
        conversation_agent: ConversationAgent
    ):
        """Initialize the Chat Agent.
        
        Args:
            db: Database session
            provider_agent: Provider Agent for chat completions
            conversation_agent: Conversation Agent for persistence
        """
        self.db = db
        self.provider_agent = provider_agent
        self.conversation_agent = conversation_agent

    def _build_messages(self, conversation: Conversation) -> List[ChatMessage]:
        """Build message list from conversation history.
        
        Args:
            conversation: Conversation to build from
            
        Returns:
            List of ChatMessage objects
        """
        messages = self.conversation_agent.get_messages(conversation)
        result = []
        for msg in messages:
            if msg.role in ("user", "assistant", "system"):
                result.append(ChatMessage(role=msg.role, content=msg.content))
        return result

    async def send_message(
        self,
        conversation: Conversation,
        user: User,
        content: str,
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
        settings: Optional[ChatSettings] = None,
        stream: bool = True,
        parent_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a message and optionally stream the response.
        
        Args:
            conversation: Conversation to send in
            user: User sending the message
            content: Message content
            provider_name: Provider to use
            model: Model to use
            settings: Chat settings
            stream: Whether to stream the response
            parent_message_id: Parent message ID for branching
            
        Returns:
            Dict with message and metadata
        """
        effective_provider = provider_name or conversation.provider
        effective_model = model or conversation.model
        effective_settings = settings or ChatSettings()
        
        # Save user message
        user_message = self.conversation_agent.add_message(
            conversation=conversation,
            role="user",
            content=content,
            provider=effective_provider,
            model=effective_model,
            parent_message_id=parent_message_id,
        )
        
        if stream:
            return {
                "message": {
                    "id": user_message.id,
                    "role": "user",
                    "content": user_message.content,
                },
                "stream": True,
            }
        
        # Non-streaming: get completion
        messages = self._build_messages(conversation)
        messages.append(ChatMessage(role="user", content=content))
        
        chat_request = ChatRequest(
            messages=messages,
            provider=effective_provider,
            model=effective_model,
            temperature=effective_settings.temperature,
            top_p=effective_settings.top_p,
            max_tokens=effective_settings.max_tokens,
            system_prompt=effective_settings.system_prompt,
            stream=False,
        )
        
        response = await self.provider_agent.chat_once(chat_request)
        
        # Save assistant message
        assistant_message = self.conversation_agent.add_message(
            conversation=conversation,
            role="assistant",
            content=response.content,
            provider=response.provider,
            model=response.model,
            tokens_prompt=response.tokens_prompt,
            tokens_completion=response.tokens_completion,
            parent_message_id=user_message.id,
        )
        
        return {
            "message": {
                "id": assistant_message.id,
                "role": "assistant",
                "content": assistant_message.content,
                "provider": assistant_message.provider,
                "model": assistant_message.model,
                "created_at": assistant_message.created_at.isoformat(),
            },
            "provider_meta": {
                "tokens_prompt": response.tokens_prompt,
                "tokens_completion": response.tokens_completion,
                "finish_reason": response.finish_reason,
            },
            "stream": False,
        }

    async def stream_message(
        self,
        conversation: Conversation,
        user: User,
        content: str,
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
        settings: Optional[ChatSettings] = None,
        parent_message_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream a chat response.
        
        Args:
            conversation: Conversation to send in
            user: User sending the message
            content: Message content
            provider_name: Provider to use
            model: Model to use
            settings: Chat settings
            parent_message_id: Parent message ID for branching
            
        Yields:
            Dict containing chunk data
        """
        effective_provider = provider_name or conversation.provider
        effective_model = model or conversation.model
        effective_settings = settings or ChatSettings()
        
        # Save user message
        user_message = self.conversation_agent.add_message(
            conversation=conversation,
            role="user",
            content=content,
            provider=effective_provider,
            model=effective_model,
            parent_message_id=parent_message_id,
        )
        
        # Yield message created event
        yield {
            "event": "message.created",
            "data": {
                "id": user_message.id,
                "role": "user",
                "content": content,
            }
        }
        
        # Build messages for the request
        messages = self._build_messages(conversation)
        messages.append(ChatMessage(role="user", content=content))
        
        chat_request = ChatRequest(
            messages=messages,
            provider=effective_provider,
            model=effective_model,
            temperature=effective_settings.temperature,
            top_p=effective_settings.top_p,
            max_tokens=effective_settings.max_tokens,
            system_prompt=effective_settings.system_prompt,
            stream=True,
        )
        
        # Start assistant message
        assistant_message_id = generate_id()
        full_response = ""
        last_chunk = {}
        
        async for chunk in self.provider_agent.chat_stream(chat_request):
            if "error" in chunk:
                yield {"event": "error", "data": {"error": chunk["error"]}}
                return
            
            # Accumulate content
            if chunk.get("content"):
                full_response += chunk["content"]
                yield {
                    "event": "message.delta",
                    "data": {
                        "id": assistant_message_id,
                        "role": "assistant",
                        "delta": chunk["content"],
                    }
                }
            
            last_chunk = chunk
        
        # Save assistant message
        assistant_message = self.conversation_agent.add_message(
            conversation=conversation,
            role="assistant",
            content=full_response,
            provider=effective_provider,
            model=last_chunk.get("model", effective_model),
            tokens_prompt=last_chunk.get("tokens_prompt"),
            tokens_completion=last_chunk.get("tokens_completion"),
            parent_message_id=user_message.id,
        )
        
        # Yield final message event
        yield {
            "event": "message.created",
            "data": {
                "id": assistant_message.id,
                "role": "assistant",
                "content": full_response,
                "provider": assistant_message.provider,
                "model": assistant_message.model,
                "tokens_prompt": assistant_message.tokens_prompt,
                "tokens_completion": assistant_message.tokens_completion,
            }
        }

    # Run management methods
    
    def create_run(
        self,
        conversation: Conversation,
        user: User,
        input_text: str = "",
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
        settings: Optional[ChatSettings] = None,
        retry_from_message_id: Optional[str] = None,
    ) -> ChatRun:
        """Create a new chat run.
        
        Args:
            conversation: Conversation for the run
            user: User initiating the run
            input_text: Input text for the run
            provider_name: Provider to use
            model: Model to use
            settings: Chat settings
            retry_from_message_id: Message ID to retry from
            
        Returns:
            Created ChatRun
        """
        run = ChatRun(
            id=generate_id(),
            user_id=user.id,
            conversation_id=conversation.id,
            provider=provider_name or conversation.provider,
            model=model or conversation.model,
            settings_json=settings.__dict__ if settings else None,
            status="running",
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        
        return run

    def get_run(self, run_id: str, user: User) -> Optional[ChatRun]:
        """Get a chat run by ID.
        
        Args:
            run_id: Run ID
            user: User requesting the run
            
        Returns:
            ChatRun if found, None otherwise
        """
        return (
            self.db.query(ChatRun)
            .filter(ChatRun.id == run_id, ChatRun.user_id == user.id)
            .first()
        )

    def cancel_run(self, run: ChatRun) -> None:
        """Cancel a chat run.
        
        Args:
            run: Run to cancel
        """
        run.status = "cancelled"
        run.cancelled_at = datetime.utcnow()
        self.db.commit()

    def retry_message(
        self,
        conversation: Conversation,
        user: User,
        message_id: str,
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
        settings: Optional[ChatSettings] = None,
    ) -> ChatRun:
        """Retry a message in a conversation.
        
        Args:
            conversation: Conversation to retry in
            user: User requesting the retry
            message_id: Message ID to retry from
            provider_name: Provider to use
            model: Model to use
            settings: Chat settings
            
        Returns:
            Created ChatRun for the retry
        """
        return self.create_run(
            conversation=conversation,
            user=user,
            provider_name=provider_name,
            model=model,
            settings=settings,
            retry_from_message_id=message_id,
        )
