"""
Session management for authentication.

Sessions are stored server-side in the database with the session token
hashed (not stored in plain text). The plain token is sent to the client
in an HttpOnly cookie.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import User, UserSession


def _utcnow_naive() -> datetime:
    """Get current UTC time as naive datetime (for SQLite compatibility)."""
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class SessionData:
    """Session data returned from session operations."""

    session_id: str
    user_id: str
    token: str  # Plain token for cookie
    csrf_token: str
    csrf_signature: str
    expires_at: datetime


def _hash_token(token: str) -> str:
    """
    Hash a session token for storage.

    Uses SHA-256 for fast, deterministic hashing.
    The token itself has sufficient entropy (32 bytes).

    Args:
        token: Plain session token.

    Returns:
        SHA-256 hex digest.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def generate_session_token() -> str:
    """
    Generate a cryptographically secure session token.

    Returns:
        URL-safe random token string (32 bytes = 43 chars base64).
    """
    return secrets.token_urlsafe(32)


def create_session(
    db: Session,
    user: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
    device_meta: str | None = None,
) -> SessionData:
    """
    Create a new session for a user.

    Rotates sessions by deleting any existing sessions for the user.

    Args:
        db: Database session.
        user: User to create session for.
        ip_address: Client IP address.
        user_agent: Client User-Agent header.
        device_meta: Optional device metadata JSON.

    Returns:
        SessionData with token and CSRF info.
    """
    from app.auth.csrf import create_signed_csrf_token

    settings = get_settings()

    # Generate tokens
    token = generate_session_token()
    token_hash = _hash_token(token)

    # Calculate expiry
    expires_at = _utcnow_naive() + timedelta(seconds=settings.session_ttl_seconds)

    # Create session record
    session = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent[:512] if user_agent else None,
        device_meta=device_meta,
    )
    db.add(session)
    db.flush()  # Get the session ID

    # Create CSRF token bound to session
    csrf_token, csrf_signature = create_signed_csrf_token(session.id)

    # Store CSRF signature in session (we'll add this field in migration)
    # For now, we compute it on-demand from the token

    db.commit()

    return SessionData(
        session_id=session.id,
        user_id=user.id,
        token=token,
        csrf_token=csrf_token,
        csrf_signature=csrf_signature,
        expires_at=expires_at,
    )


def validate_session(
    db: Session,
    token: str,
) -> tuple[UserSession, User] | None:
    """
    Validate a session token and return session + user.

    Args:
        db: Database session.
        token: Plain session token from cookie.

    Returns:
        Tuple of (UserSession, User) if valid, None otherwise.
    """
    token_hash = _hash_token(token)

    # Query session with user
    stmt = (
        select(UserSession)
        .where(UserSession.token_hash == token_hash)
        .where(UserSession.expires_at > _utcnow_naive())
    )
    session = db.execute(stmt).scalar_one_or_none()

    if not session:
        return None

    # Load user
    user = db.get(User, session.user_id)
    if not user:
        return None

    return session, user


def delete_session(db: Session, session_id: str) -> bool:
    """
    Delete a session by ID.

    Args:
        db: Database session.
        session_id: Session ID to delete.

    Returns:
        True if session was deleted.
    """
    stmt = delete(UserSession).where(UserSession.id == session_id)
    result = db.execute(stmt)
    db.commit()
    return result.rowcount > 0


def delete_user_sessions(db: Session, user_id: str) -> int:
    """
    Delete all sessions for a user.

    Args:
        db: Database session.
        user_id: User ID to delete sessions for.

    Returns:
        Number of sessions deleted.
    """
    stmt = delete(UserSession).where(UserSession.user_id == user_id)
    result = db.execute(stmt)
    db.commit()
    return result.rowcount


def cleanup_expired_sessions(db: Session) -> int:
    """
    Delete all expired sessions.

    Should be called periodically (e.g., via background task).

    Args:
        db: Database session.

    Returns:
        Number of sessions deleted.
    """
    stmt = delete(UserSession).where(UserSession.expires_at <= _utcnow_naive())
    result = db.execute(stmt)
    db.commit()
    return result.rowcount
