"""Auth service helpers for bearer authentication."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.app.auth.password import verify_password
from backend.app.auth.sessions import create_session, delete_session, get_session
from backend.app.core.security import create_access_token
from backend.app.db.models import User
from backend.app.db.repo.users_repo import get_user_by_username


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = get_user_by_username(db, username)
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


def issue_tokens(db: Session, user: User, device_meta: str | None = None) -> dict:
    access_token, expires_in = create_access_token(user.id, user.role)
    refresh_token, _ = create_session(db, user.id, device_meta=device_meta)
    return {
        "access_token": access_token,
        "expires_in": expires_in,
        "refresh_token": refresh_token,
    }


def refresh_tokens(db: Session, refresh_token: str, device_meta: str | None = None) -> tuple[dict, int] | None:
    session = get_session(db, refresh_token)
    if not session:
        return None
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user or user.status != "active":
        return None
    # Rotate refresh token
    delete_session(db, refresh_token)
    access_token, expires_in = create_access_token(user.id, user.role)
    new_refresh_token, _ = create_session(db, user.id, device_meta=device_meta)
    return (
        {
            "access_token": access_token,
            "expires_in": expires_in,
            "refresh_token": new_refresh_token,
        },
        user.id,
    )


def revoke_refresh_token(db: Session, refresh_token: str) -> bool:
    return delete_session(db, refresh_token)
