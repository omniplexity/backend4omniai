"""Authentication module for OmniAI."""

from app.auth.csrf import (
    create_signed_csrf_token,
    generate_csrf_token,
    validate_csrf_token,
    validate_origin,
)
from app.auth.dependencies import (
    CurrentUser,
    RequireAdmin,
    RequireAuth,
    ValidateCSRF,
    get_current_user,
    require_admin,
    require_auth,
    validate_csrf,
)
from app.auth.password import hash_password, needs_rehash, verify_password
from app.auth.session import (
    SessionData,
    cleanup_expired_sessions,
    create_session,
    delete_session,
    delete_user_sessions,
    validate_session,
)

__all__ = [
    # Password
    "hash_password",
    "verify_password",
    "needs_rehash",
    # CSRF
    "generate_csrf_token",
    "create_signed_csrf_token",
    "validate_csrf_token",
    "validate_origin",
    # Session
    "SessionData",
    "create_session",
    "delete_session",
    "delete_user_sessions",
    "validate_session",
    "cleanup_expired_sessions",
    # Dependencies
    "get_current_user",
    "require_auth",
    "require_admin",
    "validate_csrf",
    # Type aliases
    "CurrentUser",
    "RequireAuth",
    "RequireAdmin",
    "ValidateCSRF",
]
