"""v1 conversations endpoints.

These endpoints use the Conversation Agent for conversation management.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_current_user
from backend.db import get_db
from backend.db.models import Conversation, Message, User
from backend.agents.conversation import ConversationAgent

router = APIRouter(prefix="/conversations", tags=["v1-conversations"])


class ConversationModel(BaseModel):
    """Conversation response model."""
    id: str
    title: str
    provider: Optional[str]
    model: Optional[str]
    project_id: Optional[str] = None
    parent_conversation_id: Optional[str] = None
    branched_from_message_id: Optional[str] = None
    created_at: str
    updated_at: str
    settings: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None
    preset_id: Optional[str] = None


class MessageModel(BaseModel):
    """Message response model."""
    id: str
    role: str
    content: str
    provider: Optional[str] = None
    model: Optional[str] = None
    tokens_prompt: Optional[int] = None
    tokens_completion: Optional[int] = None
    parent_message_id: Optional[str] = None
    revision_of_message_id: Optional[str] = None
    provider_meta: Optional[Dict[str, Any]] = None
    created_at: str


class CreateConversationRequest(BaseModel):
    """Create conversation request."""
    title: str = Field(default="New Conversation")
    provider: Optional[str] = None
    model: Optional[str] = None
    project_id: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None
    preset_id: Optional[str] = None


class UpdateConversationRequest(BaseModel):
    """Update conversation request."""
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    project_id: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None
    preset_id: Optional[str] = None


class SendMessageRequest(BaseModel):
    """Send message request."""
    content: str = Field(min_length=1)
    provider: Optional[str] = None
    model: Optional[str] = None
    stream: bool = True
    settings: Optional[Dict[str, Any]] = None


def _create_conversation_agent(db: DBSession) -> ConversationAgent:
    """Create a Conversation Agent instance."""
    return ConversationAgent(db)


@router.get("", response_model=List[ConversationModel])
async def list_conversations(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List user's conversations."""
    conversation_agent = _create_conversation_agent(db)
    conversations = conversation_agent.list_conversations(current_user, limit, offset)
    
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
            settings=c.settings_json or None,
            system_prompt=c.system_prompt,
            preset_id=c.preset_id,
        )
        for c in conversations
    ]


@router.post("", response_model=ConversationModel)
async def create_conversation(
    body: CreateConversationRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new conversation."""
    conversation_agent = _create_conversation_agent(db)
    
    conversation = conversation_agent.create_conversation(
        current_user,
        title=body.title,
        provider=body.provider,
        model=body.model,
        project_id=body.project_id,
        system_prompt=body.system_prompt,
        settings_json=body.settings,
        preset_id=body.preset_id,
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
        settings=conversation.settings_json or None,
        system_prompt=conversation.system_prompt,
        preset_id=conversation.preset_id,
    )


@router.get("/{conversation_id}", response_model=ConversationModel)
async def get_conversation(
    conversation_id: str,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a conversation by ID."""
    conversation_agent = _create_conversation_agent(db)
    
    conversation = conversation_agent.get_conversation(conversation_id, current_user)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    
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
        settings=conversation.settings_json or None,
        system_prompt=conversation.system_prompt,
        preset_id=conversation.preset_id,
    )


@router.patch("/{conversation_id}", response_model=ConversationModel)
async def update_conversation(
    conversation_id: str,
    body: UpdateConversationRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a conversation."""
    conversation_agent = _create_conversation_agent(db)
    
    conversation = conversation_agent.get_conversation(conversation_id, current_user)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    conversation = conversation_agent.update_conversation(
        conversation,
        title=body.title,
        project_id=body.project_id,
        system_prompt=body.system_prompt,
        settings_json=body.settings,
        preset_id=body.preset_id,
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
        settings=conversation.settings_json or None,
        system_prompt=conversation.system_prompt,
        preset_id=conversation.preset_id,
    )


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a conversation."""
    conversation_agent = _create_conversation_agent(db)
    
    conversation = conversation_agent.get_conversation(conversation_id, current_user)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    conversation_agent.delete_conversation(conversation)
    return {"deleted": True, "id": conversation_id}


@router.get("/{conversation_id}/messages", response_model=List[MessageModel])
async def list_messages(
    conversation_id: str,
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get messages in a conversation."""
    conversation_agent = _create_conversation_agent(db)
    
    conversation = conversation_agent.get_conversation(conversation_id, current_user)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    messages = conversation_agent.get_messages(conversation, limit=500)
    
    return [
        MessageModel(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            provider=msg.provider,
            model=msg.model,
            tokens_prompt=msg.tokens_prompt,
            tokens_completion=msg.tokens_completion,
            parent_message_id=msg.parent_message_id,
            revision_of_message_id=msg.revision_of_message_id,
            provider_meta=msg.provider_meta_json,
            created_at=msg.created_at.isoformat(),
        )
        for msg in messages
    ]


@router.post("/{conversation_id}/branch", response_model=ConversationModel)
async def branch_conversation(
    conversation_id: str,
    from_message_id: str,
    title: Optional[str] = None,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Branch a conversation from a message."""
    conversation_agent = _create_conversation_agent(db)
    
    conversation = conversation_agent.get_conversation(conversation_id, current_user)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    new_conversation = conversation_agent.branch_conversation(
        conversation,
        from_message_id=from_message_id,
        user=current_user,
        title=title,
    )

    return ConversationModel(
        id=new_conversation.id,
        title=new_conversation.title,
        provider=new_conversation.provider,
        model=new_conversation.model,
        project_id=new_conversation.project_id,
        parent_conversation_id=new_conversation.parent_conversation_id,
        branched_from_message_id=new_conversation.branched_from_message_id,
        created_at=new_conversation.created_at.isoformat(),
        updated_at=new_conversation.updated_at.isoformat(),
        settings=new_conversation.settings_json or None,
        system_prompt=new_conversation.system_prompt,
        preset_id=new_conversation.preset_id,
    )
