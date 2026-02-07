"""FastAPI dependencies for authentication."""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session as DBSession

from backend.config import get_settings
from backend.core.exceptions import AuthenticationError
from backend.db import get_db
from backend.db.models import User
from backend.auth.session import validate_session


async def get_current_user(
    request: Request,
    db: DBSession = Depends(get_db),
) -> User:
    """Get the current authenticated user.

    Raises:
        HTTPException: If not authenticated.
    """
    settings = get_settings()

    # Get session token from cookie
    session_token = request.cookies.get(settings.session_cookie_name)

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate session
    session = validate_session(db, session_token)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Load user
    user = db.query(User).filter(User.id == session.user_id).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


async def get_optional_user(
    request: Request,
    db: DBSession = Depends(get_db),
) -> Optional[User]:
    """Get the current user if authenticated, otherwise None."""
    settings = get_settings()

    session_token = request.cookies.get(settings.session_cookie_name)

    if not session_token:
        return None

    session = validate_session(db, session_token)

    if not session:
        return None

    user = db.query(User).filter(User.id == session.user_id).first()

    if not user or not user.is_active:
        return None

    return user


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require admin privileges."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
