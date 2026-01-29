"""
FastAPI dependencies for authentication.

These dependencies are used to protect routes and extract
the current user from the session.
"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.csrf import validate_origin
from app.auth.session import validate_session
from app.config import get_settings
from app.core import (
    AccountDisabledError,
    CSRFError,
    ForbiddenError,
    SessionExpiredError,
    UnauthorizedError,
)
from app.db import get_db
from app.db.models import User, UserSession


def get_session_token(request: Request) -> str | None:
    """
    Extract session token from cookie.

    Args:
        request: FastAPI request object.

    Returns:
        Session token if present, None otherwise.
    """
    settings = get_settings()
    return request.cookies.get(settings.session_cookie_name)


def get_csrf_token_header(request: Request) -> str | None:
    """
    Extract CSRF token from header.

    Args:
        request: FastAPI request object.

    Returns:
        CSRF token if present, None otherwise.
    """
    settings = get_settings()
    return request.headers.get(settings.csrf_header_name)


def get_csrf_token_cookie(request: Request) -> str | None:
    """
    Extract CSRF token from cookie.

    Args:
        request: FastAPI request object.

    Returns:
        CSRF token if present, None otherwise.
    """
    settings = get_settings()
    return request.cookies.get(settings.csrf_cookie_name)


async def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> tuple[User, UserSession] | None:
    """
    Get current authenticated user from session cookie.

    Does NOT enforce authentication - returns None if not authenticated.
    Use require_auth() dependency to enforce authentication.

    Args:
        request: FastAPI request object.
        db: Database session.

    Returns:
        Tuple of (User, UserSession) if authenticated, None otherwise.
    """
    token = get_session_token(request)
    if not token:
        return None

    result = validate_session(db, token)
    if not result:
        return None

    session, user = result
    if user.status != "active":
        return None

    return user, session


async def require_auth(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> tuple[User, UserSession]:
    """
    Require authentication - raises if not authenticated.

    Args:
        request: FastAPI request object.
        db: Database session.

    Returns:
        Tuple of (User, UserSession).

    Raises:
        UnauthorizedError: If no session cookie.
        SessionExpiredError: If session is expired/invalid.
        AccountDisabledError: If user account is disabled.
    """
    token = get_session_token(request)
    if not token:
        raise UnauthorizedError("Authentication required")

    result = validate_session(db, token)
    if not result:
        raise SessionExpiredError("Session expired or invalid")

    session, user = result

    if user.status == "disabled":
        raise AccountDisabledError("Account is disabled")

    if user.status != "active":
        raise UnauthorizedError("Account not active")

    return user, session


async def require_admin(
    auth: Annotated[tuple[User, UserSession], Depends(require_auth)],
) -> tuple[User, UserSession]:
    """
    Require admin role - raises if not admin.

    Args:
        auth: Authenticated user tuple from require_auth.

    Returns:
        Tuple of (User, UserSession).

    Raises:
        ForbiddenError: If user is not admin.
    """
    user, session = auth
    if user.role != "admin":
        raise ForbiddenError("Admin access required")
    return user, session


async def validate_csrf(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """
    Validate CSRF token for state-changing requests.

    This is typically used as a dependency on POST/PUT/PATCH/DELETE routes.

    Args:
        request: FastAPI request object.
        db: Database session.

    Raises:
        CSRFError: If CSRF validation fails.
    """
    settings = get_settings()

    # Skip CSRF for safe methods
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    # Validate Origin/Referer (best effort)
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    if not validate_origin(origin, referer, settings.cors_origins_list):
        raise CSRFError("Invalid origin")

    # Get session token
    session_token = get_session_token(request)
    if not session_token:
        # No session = no CSRF needed (request will fail auth anyway)
        return

    # Validate session and get session ID
    result = validate_session(db, session_token)
    if not result:
        # Invalid session = no CSRF needed (request will fail auth anyway)
        return

    session, _ = result

    # Get CSRF tokens
    csrf_header = get_csrf_token_header(request)
    csrf_cookie = get_csrf_token_cookie(request)

    # Both must be present and match
    if not csrf_header or not csrf_cookie:
        raise CSRFError("CSRF token missing")

    if csrf_header != csrf_cookie:
        raise CSRFError("CSRF token mismatch")

    # The double-submit cookie pattern (header == cookie) provides protection.
    # A more secure option would be to store the CSRF signature per-session,
    # but this approach is sufficient for most use cases.
    return


# Type aliases for cleaner dependency injection
CurrentUser = Annotated[tuple[User, UserSession] | None, Depends(get_current_user)]
RequireAuth = Annotated[tuple[User, UserSession], Depends(require_auth)]
RequireAdmin = Annotated[tuple[User, UserSession], Depends(require_admin)]
ValidateCSRF = Annotated[None, Depends(validate_csrf)]
