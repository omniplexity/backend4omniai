"""Repository helpers for conversations and messages."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Conversation, Message


def create_conversation(
    db: Session,
    user_id: str,
    title: str | None = None,
    model: str | None = None,
    system_prompt: str | None = None,
) -> Conversation:
    """Create a new conversation for the given user."""
    conversation = Conversation(
        user_id=user_id,
        title=title.strip() if title and title.strip() else "New Chat",
        model=model,
        system_prompt=system_prompt,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_user_conversation(
    db: Session, user_id: str, conversation_id: str
) -> Conversation | None:
    """Fetch conversation owned by user."""
    stmt = (
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def list_user_conversations(db: Session, user_id: str) -> list[Conversation]:
    """List conversations belonging to the user."""
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    return db.execute(stmt).scalars().all()


def update_conversation_title(
    db: Session, user_id: str, conversation_id: str, title: str
) -> Conversation | None:
    """Rename an existing conversation."""
    conversation = get_user_conversation(db, user_id, conversation_id)
    if not conversation:
        return None
    conversation.title = title.strip() if title.strip() else conversation.title
    db.commit()
    db.refresh(conversation)
    return conversation


def delete_conversation(db: Session, user_id: str, conversation_id: str) -> bool:
    """Delete a conversation and cascade its messages."""
    conversation = get_user_conversation(db, user_id, conversation_id)
    if not conversation:
        return False
    db.delete(conversation)
    db.commit()
    return True


def create_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    provider_meta: str | None = None,
) -> Message:
    """Insert a chat message."""
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        provider_meta=provider_meta,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def get_conversation_messages(db: Session, conversation_id: str) -> list[Message]:
    """Get all messages for a conversation ordered by creation time."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return db.execute(stmt).scalars().all()


def get_last_user_message(db: Session, conversation_id: str) -> Message | None:
    """Get the most recent user message in a conversation."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.role == "user")
        .order_by(Message.created_at.desc())
    )
    return db.execute(stmt).scalar_one_or_none()


def get_last_assistant_message_after(
    db: Session, conversation_id: str, after: datetime | None = None
) -> Message | None:
    """Get the most recent assistant message optionally after a timestamp."""
    stmt = select(Message).where(
        Message.conversation_id == conversation_id, Message.role == "assistant"
    )
    if after:
        stmt = stmt.where(Message.created_at >= after)
    stmt = stmt.order_by(Message.created_at.desc())
    return db.execute(stmt).scalar_one_or_none()
