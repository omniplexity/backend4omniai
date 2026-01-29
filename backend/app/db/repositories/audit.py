"""
Audit log repository for security event tracking.
"""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import request_id_ctx
from app.db.models import AuditLog


class AuditAction:
    """Audit action constants."""

    # Authentication
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    REGISTER = "register"
    SESSION_CREATE = "session_create"
    SESSION_DELETE = "session_delete"

    # User management
    USER_DISABLE = "user_disable"
    USER_ENABLE = "user_enable"
    USER_ENABLE = "user_enable"

    # Invite management
    INVITE_CREATE = "invite_create"
    INVITE_USE = "invite_use"
    USER_QUOTA_UPDATE = "user_quota_update"


def log_audit(
    db: Session,
    action: str,
    actor_user_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """
    Create an audit log entry.

    Args:
        db: Database session.
        action: Action being logged (use AuditAction constants).
        actor_user_id: User performing the action (None for anonymous).
        target_type: Type of target (e.g., "user", "invite", "session").
        target_id: ID of the target resource.
        details: Additional details as dict (stored as JSON).
        ip_address: Client IP address.
        user_agent: Client User-Agent header.

    Returns:
        Created AuditLog entry.
    """
    # Get request ID from context if available
    request_id = request_id_ctx.get(None)

    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=json.dumps(details) if details else None,
        ip_address=ip_address,
        user_agent=user_agent[:512] if user_agent else None,
        request_id=request_id,
    )
    db.add(entry)
    db.commit()
    return entry


def log_login(
    db: Session,
    user_id: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    success: bool = True,
) -> AuditLog:
    """Log a login attempt."""
    return log_audit(
        db,
        action=AuditAction.LOGIN if success else AuditAction.LOGIN_FAILED,
        actor_user_id=user_id if success else None,
        target_type="user",
        target_id=user_id,
        details={"success": success},
        ip_address=ip_address,
        user_agent=user_agent,
    )


def log_logout(
    db: Session,
    user_id: str,
    session_id: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Log a logout."""
    return log_audit(
        db,
        action=AuditAction.LOGOUT,
        actor_user_id=user_id,
        target_type="session",
        target_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def log_register(
    db: Session,
    user_id: str,
    username: str,
    invite_code: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Log a user registration."""
    return log_audit(
        db,
        action=AuditAction.REGISTER,
        actor_user_id=user_id,
        target_type="user",
        target_id=user_id,
        details={"username": username, "invite_code": invite_code},
        ip_address=ip_address,
        user_agent=user_agent,
    )


def log_session_create(
    db: Session,
    user_id: str,
    session_id: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Log session creation."""
    return log_audit(
        db,
        action=AuditAction.SESSION_CREATE,
        actor_user_id=user_id,
        target_type="session",
        target_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def log_invite_create(
    db: Session,
    admin_user_id: str,
    invite_id: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Log invite creation."""
    return log_audit(
        db,
        action=AuditAction.INVITE_CREATE,
        actor_user_id=admin_user_id,
        target_type="invite",
        target_id=invite_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def log_user_disable(
    db: Session,
    admin_user_id: str,
    target_user_id: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Log user disable action."""
    return log_audit(
        db,
        action=AuditAction.USER_DISABLE,
        actor_user_id=admin_user_id,
        target_type="user",
        target_id=target_user_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def list_audit_entries(db: Session, *, limit: int = 200, offset: int = 0) -> list[AuditLog]:
    """Return recent audit entries."""
    stmt = (
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return db.execute(stmt).scalars().all()
