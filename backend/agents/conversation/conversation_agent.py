"""Conversation Agent.

Manages conversations, messages, and context blocks.
Provides CRUD operations for conversations and message persistence.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session as DBSession

from backend.db.models import User, Conversation, Message, ContextBlock, generate_id
from backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ConversationInfo:
    """Conversation information."""
    id: str
    title: str
    provider: Optional[str]
    model: Optional[str]
    project_id: Optional[str]
    parent_conversation_id: Optional[str]
    branched_from_message_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    settings_json: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None
    preset_id: Optional[str] = None


@dataclass
class MessageInfo:
    """Message information."""
    id: str
    role: str
    content: str
    conversation_id: str
    provider: Optional[str]
    model: Optional[str]
    tokens_prompt: Optional[int]
    tokens_completion: Optional[int]
    parent_message_id: Optional[str]
    revision_of_message_id: Optional[str]
    provider_meta_json: Optional[Dict[str, Any]]
    created_at: datetime


@dataclass
class ContextBlockInfo:
    """Context block information."""
    id: str
    title: str
    content: str
    enabled: bool
    created_at: datetime


class ConversationAgent:
    """Agent for managing conversations."""

    def __init__(self, db: DBSession):
        """Initialize the Conversation Agent.
        
        Args:
            db: Database session
        """
        self.db = db

    def create_conversation(
        self,
        user: User,
        title: str = "New Conversation",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        project_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        settings_json: Optional[Dict[str, Any]] = None,
        preset_id: Optional[str] = None,
    ) -> Conversation:
        """Create a new conversation.
        
        Args:
            user: User creating the conversation
            title: Conversation title
            provider: Default provider
            model: Default model
            project_id: Optional project ID
            system_prompt: Optional system prompt
            settings_json: Optional settings JSON
            preset_id: Optional preset ID
            
        Returns:
            Created Conversation
        """
        conversation = Conversation(
            id=generate_id(),
            user_id=user.id,
            title=title,
            provider=provider,
            model=model,
            project_id=project_id,
            system_prompt=system_prompt,
            settings_json=settings_json,
            preset_id=preset_id,
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        
        logger.info(f"Created conversation {conversation.id} for user {user.id}")
        return conversation

    def list_conversations(
        self,
        user: User,
        limit: int = 50,
        offset: int = 0
    ) -> List[Conversation]:
        """List user's conversations.
        
        Args:
            user: User to list conversations for
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of Conversation objects
        """
        return (
            self.db.query(Conversation)
            .filter(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_conversation(
        self,
        conversation_id: str,
        user: User
    ) -> Optional[Conversation]:
        """Get a conversation by ID.
        
        Args:
            conversation_id: Conversation ID
            user: User requesting the conversation
            
        Returns:
            Conversation if found and owned by user, None otherwise
        """
        return (
            self.db.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id
            )
            .first()
        )

    def update_conversation(
        self,
        conversation: Conversation,
        title: Optional[str] = None,
        project_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        settings_json: Optional[Dict[str, Any]] = None,
        preset_id: Optional[str] = None,
    ) -> Conversation:
        """Update a conversation.
        
        Args:
            conversation: Conversation to update
            title: New title (optional)
            project_id: New project ID (optional)
            system_prompt: New system prompt (optional)
            settings_json: New settings (optional)
            preset_id: New preset ID (optional)
            
        Returns:
            Updated Conversation
        """
        if title is not None:
            conversation.title = title
        if project_id is not None:
            conversation.project_id = project_id
        if system_prompt is not None:
            conversation.system_prompt = system_prompt
        if settings_json is not None:
            conversation.settings_json = settings_json
        if preset_id is not None:
            conversation.preset_id = preset_id
            
        self.db.commit()
        self.db.refresh(conversation)
        
        return conversation

    def delete_conversation(self, conversation: Conversation) -> None:
        """Delete a conversation.
        
        Args:
            conversation: Conversation to delete
        """
        self.db.delete(conversation)
        self.db.commit()
        logger.info(f"Deleted conversation {conversation.id}")

    def branch_conversation(
        self,
        conversation: Conversation,
        from_message_id: str,
        user: User,
        title: Optional[str] = None
    ) -> Conversation:
        """Create a branch of a conversation from a message.
        
        Args:
            conversation: Source conversation
            from_message_id: Message ID to branch from
            user: User creating the branch
            title: Optional new title
            
        Returns:
            New Conversation that is a branch
        """
        # Get source messages
        source_messages = (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.asc())
            .all()
        )
        
        # Find cutoff index
        cutoff_index = None
        for idx, msg in enumerate(source_messages):
            if msg.id == from_message_id:
                cutoff_index = idx
                break
                
        if cutoff_index is None:
            raise ValueError(f"Message not found: {from_message_id}")
        
        # Create new conversation
        new_title = title or f"{conversation.title} (branch)"
        new_convo = self.create_conversation(
            user=user,
            title=new_title,
            provider=conversation.provider,
            model=conversation.model,
            project_id=conversation.project_id,
            system_prompt=conversation.system_prompt,
            settings_json=conversation.settings_json,
            preset_id=conversation.preset_id,
        )
        
        new_convo.parent_conversation_id = conversation.id
        new_convo.branched_from_message_id = from_message_id
        self.db.commit()
        self.db.refresh(new_convo)
        
        # Copy messages up to cutoff
        for msg in source_messages[:cutoff_index + 1]:
            clone = Message(
                id=generate_id(),
                conversation_id=new_convo.id,
                role=msg.role,
                content=msg.content,
                tokens_prompt=msg.tokens_prompt,
                tokens_completion=msg.tokens_completion,
                provider=msg.provider,
                model=msg.model,
                created_at=msg.created_at,
            )
            self.db.add(clone)
        self.db.commit()
        
        logger.info(f"Branched conversation {new_convo.id} from {conversation.id}")
        return new_convo

    def add_message(
        self,
        conversation: Conversation,
        role: str,
        content: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        tokens_prompt: Optional[int] = None,
        tokens_completion: Optional[int] = None,
        parent_message_id: Optional[str] = None,
        provider_meta_json: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """Add a message to a conversation.
        
        Args:
            conversation: Conversation to add message to
            role: Message role (user, assistant, system)
            content: Message content
            provider: Provider used
            model: Model used
            tokens_prompt: Prompt tokens
            tokens_completion: Completion tokens
            parent_message_id: Parent message ID
            provider_meta_json: Provider metadata
            
        Returns:
            Created Message
        """
        message = Message(
            id=generate_id(),
            conversation_id=conversation.id,
            role=role,
            content=content,
            provider=provider,
            model=model,
            tokens_prompt=tokens_prompt,
            tokens_completion=tokens_completion,
            parent_message_id=parent_message_id,
            provider_meta_json=provider_meta_json,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        
        # Update conversation timestamp
        conversation.updated_at = message.created_at
        self.db.commit()
        
        return message

    def get_messages(
        self,
        conversation: Conversation,
        limit: int = 500
    ) -> List[Message]:
        """Get messages in a conversation.
        
        Args:
            conversation: Conversation to get messages from
            limit: Maximum number of messages
            
        Returns:
            List of Message objects
        """
        return (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.asc())
            .limit(limit)
            .all()
        )

    def get_message(
        self,
        message_id: str,
        user: User
    ) -> Optional[Message]:
        """Get a message by ID.
        
        Args:
            message_id: Message ID
            user: User requesting the message
            
        Returns:
            Message if found, None otherwise
        """
        message = (
            self.db.query(Message)
            .join(Conversation)
            .filter(
                Message.id == message_id,
                Conversation.user_id == user.id
            )
            .first()
        )
        return message

    # Context Block operations
    
    def create_context_block(
        self,
        user: User,
        title: str,
        content: str,
        project_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        enabled: bool = True,
    ) -> ContextBlock:
        """Create a context block.
        
        Args:
            user: User creating the block
            title: Block title
            content: Block content
            project_id: Optional project ID
            conversation_id: Optional conversation ID
            enabled: Whether block is enabled
            
        Returns:
            Created ContextBlock
        """
        block = ContextBlock(
            id=generate_id(),
            user_id=user.id,
            title=title,
            content=content,
            project_id=project_id,
            conversation_id=conversation_id,
            enabled=enabled,
        )
        self.db.add(block)
        self.db.commit()
        self.db.refresh(block)
        
        return block

    def get_context_blocks(
        self,
        user: User,
        project_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[ContextBlock]:
        """Get context blocks for a user.
        
        Args:
            user: User to get blocks for
            project_id: Optional project filter
            conversation_id: Optional conversation filter
            enabled_only: Only return enabled blocks
            
        Returns:
            List of ContextBlock objects
        """
        query = (
            self.db.query(ContextBlock)
            .filter(ContextBlock.user_id == user.id)
        )
        
        if project_id:
            query = query.filter(
                (ContextBlock.project_id == project_id) | 
                (ContextBlock.project_id.is_(None))
            )
        if conversation_id:
            query = query.filter(
                (ContextBlock.conversation_id == conversation_id) |
                (ContextBlock.conversation_id.is_(None))
            )
        if enabled_only:
            query = query.filter(ContextBlock.enabled == True)
            
        return query.order_by(ContextBlock.created_at.asc()).all()

    def update_context_block(
        self,
        block: ContextBlock,
        title: Optional[str] = None,
        content: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> ContextBlock:
        """Update a context block.
        
        Args:
            block: Block to update
            title: New title
            content: New content
            enabled: New enabled status
            
        Returns:
            Updated ContextBlock
        """
        if title is not None:
            block.title = title
        if content is not None:
            block.content = content
        if enabled is not None:
            block.enabled = enabled
            
        self.db.commit()
        self.db.refresh(block)
        
        return block

    def delete_context_block(self, block: ContextBlock) -> None:
        """Delete a context block.
        
        Args:
            block: Block to delete
        """
        self.db.delete(block)
        self.db.commit()
