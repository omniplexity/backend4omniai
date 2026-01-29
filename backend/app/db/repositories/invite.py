"""
Invite repository for database operations.
"""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Invite


def _utcnow_naive() -> datetime:
    """Get current UTC time as naive datetime (for SQLite compatibility)."""
    return datetime.now(UTC).replace(tzinfo=None)


def generate_invite_code() -> str:
    """Generate a secure invite code."""
    return secrets.token_urlsafe(16)


def create_invite(
    db: Session,
    created_by: str,
    expires_in_seconds: int = 604800,  # 7 days default
    max_uses: int = 1,
) -> Invite:
    """
    Create a new invite code.

    Args:
        db: Database session.
        created_by: User ID of admin creating the invite.
        expires_in_seconds: Time until invite expires.
        max_uses: Maximum number of times invite can be used.

    Returns:
        Created Invite object.
    """
    code = generate_invite_code()
    expires_at = _utcnow_naive() + timedelta(seconds=expires_in_seconds)

    invite = Invite(
        code=code,
        created_by=created_by,
        expires_at=expires_at,
        max_uses=max_uses,
        use_count=0,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


def get_invite_by_code(db: Session, code: str) -> Invite | None:
    """Get invite by code."""
    stmt = select(Invite).where(Invite.code == code)
    return db.execute(stmt).scalar_one_or_none()


def validate_invite(db: Session, code: str) -> Invite | None:
    """
    Validate an invite code.

    Returns the invite if valid, None if invalid/expired/used.

    Args:
        db: Database session.
        code: Invite code to validate.

    Returns:
        Invite if valid, None otherwise.
    """
    invite = get_invite_by_code(db, code)
    if not invite:
        return None

    # Check expiry
    if invite.expires_at <= _utcnow_naive():
        return None

    # Check uses
    if invite.use_count >= invite.max_uses:
        return None

    return invite


def use_invite(db: Session, invite: Invite, user_id: str) -> None:
    """
    Mark an invite as used.

    Args:
        db: Database session.
        invite: Invite to mark as used.
        user_id: User ID who used the invite.
    """
    invite.use_count += 1
    invite.used_by = user_id
    invite.used_at = _utcnow_naive()
    db.commit()


def get_invites_by_creator(db: Session, creator_id: str) -> list[Invite]:
    """Get all invites created by a user."""
    stmt = (
        select(Invite)
        .where(Invite.created_by == creator_id)
        .order_by(Invite.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def get_all_invites(db: Session, limit: int = 100) -> list[Invite]:
    """Get all invites (admin view)."""
    stmt = select(Invite).order_by(Invite.created_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())
