"""Conversation helpers that enforce ownership invariants."""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.db.models import Conversation, Project
from backend.app.services.chat_service import create_conversation_service


def _resolve_project_id(db: Session, user_id: int, project_id: int | None) -> int | None:
    if not project_id:
        return None
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
    return project.id if project else None


def ensure_conversation(
    db: Session,
    user_id: int,
    conversation_id: int | None = None,
    project_id: int | None = None,
) -> Conversation:
    """Ensure a conversation exists for the user; create if missing or not owned."""
    if conversation_id:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()
        if conversation:
            return conversation

    resolved_project_id = _resolve_project_id(db, user_id, project_id)
    return create_conversation_service(db, user_id, project_id=resolved_project_id)
