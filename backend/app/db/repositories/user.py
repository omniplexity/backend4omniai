"""
User repository for database operations.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User


def get_user_by_id(db: Session, user_id: str) -> User | None:
    """Get user by ID."""
    return db.get(User, user_id)


def get_user_by_username(db: Session, username: str) -> User | None:
    """Get user by username (case-insensitive)."""
    stmt = select(User).where(User.username.ilike(username))
    return db.execute(stmt).scalar_one_or_none()


def get_user_by_email(db: Session, email: str) -> User | None:
    """Get user by email (case-insensitive)."""
    if not email:
        return None
    stmt = select(User).where(User.email.ilike(email))
    return db.execute(stmt).scalar_one_or_none()


def get_user_by_username_or_email(db: Session, identifier: str) -> User | None:
    """Get user by username or email (for login)."""
    # Try username first
    user = get_user_by_username(db, identifier)
    if user:
        return user
    # Try email
    return get_user_by_email(db, identifier)


def create_user(
    db: Session,
    username: str,
    password_hash: str,
    email: str | None = None,
    role: str = "user",
    status: str = "active",
) -> User:
    """
    Create a new user.

    Args:
        db: Database session.
        username: Unique username.
        password_hash: Argon2id password hash.
        email: Optional email address.
        role: User role (default "user").
        status: User status (default "active").

    Returns:
        Created User object.
    """
    user = User(
        username=username,
        email=email.lower() if email else None,
        password_hash=password_hash,
        role=role,
        status=status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user_status(db: Session, user_id: str, status: str) -> User | None:
    """
    Update user status.

    Args:
        db: Database session.
        user_id: User ID.
        status: New status (active/disabled).

    Returns:
        Updated User or None if not found.
    """
    user = get_user_by_id(db, user_id)
    if not user:
        return None

    user.status = status
    db.commit()
    db.refresh(user)
    return user


def update_last_login(db: Session, user: User) -> None:
    """Update user's last login timestamp."""
    from datetime import UTC, datetime

    user.last_login = datetime.now(UTC)
    db.commit()


def username_exists(db: Session, username: str) -> bool:
    """Check if username is taken."""
    return get_user_by_username(db, username) is not None


def email_exists(db: Session, email: str) -> bool:
    """Check if email is taken."""
    if not email:
        return False
    return get_user_by_email(db, email) is not None
