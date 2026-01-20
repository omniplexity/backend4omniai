from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.db.models import Invite


def create_invite(
    session: Session,
    code: str,
    expires_at: datetime,
    created_by: Optional[int] = None,
    used_by: Optional[int] = None,
    revoked_at: Optional[datetime] = None,
) -> Invite:
    """Create a new invite."""
    invite = Invite(
        code=code,
        created_by=created_by,
        used_by=used_by,
        expires_at=expires_at,
        revoked_at=revoked_at,
    )
    session.add(invite)
    session.flush()
    return invite


def consume_invite(session: Session, code: str, used_by: int) -> Optional[Invite]:
    """Consume an invite by setting used_by."""
    invite = session.query(Invite).filter(
        Invite.code == code,
        Invite.used_by.is_(None),
        Invite.revoked_at.is_(None),
        Invite.expires_at > datetime.now(timezone.utc)
    ).first()
    if invite:
        invite.used_by = used_by
        session.flush()
    return invite


def get_invite(session: Session, code: str) -> Optional[Invite]:
    """Get an invite by code."""
    return session.query(Invite).filter(Invite.code == code).first()