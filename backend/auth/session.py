"""Session management for authentication."""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session as DBSession

from backend.config import get_settings
from backend.core.time import utcnow
from backend.db.models import Session, User


def _hash_token(token: str) -> str:
    """Hash a session token."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: DBSession, user: User) -> Tuple[str, str]:
    """Create a new session for a user.

    Returns:
        Tuple of (session_token, csrf_token)
    """
    settings = get_settings()

    # Generate tokens
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)

    # Create session record
    session = Session(
        user_id=user.id,
        token_hash=_hash_token(session_token),
        csrf_token=csrf_token,
        expires_at=utcnow() + timedelta(seconds=settings.session_ttl_seconds),
    )

    db.add(session)
    db.commit()

    return session_token, csrf_token


def rotate_session(db: DBSession, session_token: str) -> Optional[Tuple[str, str, Session]]:
    """Rotate an existing session (token + CSRF), returning new tokens.

    This is used for explicit refresh/renew behavior:
    - If the old session is valid, delete it and create a new one.
    - Returns (new_session_token, new_csrf_token, new_session_row)
    """
    settings = get_settings()

    existing = validate_session(db, session_token)
    if not existing:
        return None

    # Generate new tokens
    new_session_token = secrets.token_urlsafe(32)
    new_csrf_token = secrets.token_urlsafe(32)

    new_row = Session(
        user_id=existing.user_id,
        token_hash=_hash_token(new_session_token),
        csrf_token=new_csrf_token,
        expires_at=utcnow() + timedelta(seconds=settings.session_ttl_seconds),
    )

    # Replace in one transaction
    db.delete(existing)
    db.add(new_row)
    db.commit()
    db.refresh(new_row)

    return new_session_token, new_csrf_token, new_row


def validate_session(db: DBSession, session_token: str) -> Optional[Session]:
    """Validate a session token and return the session if valid."""
    if not session_token:
        return None

    token_hash = _hash_token(session_token)
    session = db.query(Session).filter(
        Session.token_hash == token_hash,
        Session.expires_at > utcnow(),
    ).first()

    return session


def invalidate_session(db: DBSession, session_token: str) -> bool:
    """Invalidate a session."""
    if not session_token:
        return False

    token_hash = _hash_token(session_token)
    result = db.query(Session).filter(Session.token_hash == token_hash).delete()
    db.commit()

    return result > 0


def cleanup_expired_sessions(db: DBSession) -> int:
    """Remove expired sessions."""
    result = db.query(Session).filter(Session.expires_at <= utcnow()).delete()
    db.commit()
    return result


def hash_session_token(token: str) -> str:
    """Public helper for matching current cookie to a session row."""
    return _hash_token(token)


def get_user_sessions(db: DBSession, user_id: str) -> List[Session]:
    """Get all active sessions for a user.
    
    Returns only non-expired sessions ordered by creation date.
    """
    return db.query(Session).filter(
        Session.user_id == user_id,
        Session.expires_at > utcnow(),
    ).order_by(Session.created_at.desc()).all()


def revoke_all_user_sessions(db: DBSession, user_id: str, except_session_id: Optional[str] = None) -> int:
    """Revoke all sessions for a user.
    
    Args:
        db: Database session
        user_id: User ID to revoke sessions for
        except_session_id: Optional session ID to preserve (e.g., admin's current session)
        
    Returns:
        Number of sessions revoked
    """
    query = db.query(Session).filter(
        Session.user_id == user_id,
        Session.expires_at > utcnow(),
    )
    
    if except_session_id:
        query = query.filter(Session.id != except_session_id)
    
    count = query.count()
    query.delete(synchronize_session=False)
    db.commit()
    
    return count


def revoke_session_by_id(db: DBSession, session_id: str) -> bool:
    """Revoke a specific session by its ID.
    
    Returns:
        True if a session was found and deleted, False otherwise
    """
    result = db.query(Session).filter(Session.id == session_id).delete()
    db.commit()
    return result > 0
