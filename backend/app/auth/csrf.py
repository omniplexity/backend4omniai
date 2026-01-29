"""
CSRF token management.

CSRF tokens are bound to user sessions and validated on state-changing requests.
The token is stored in a non-HttpOnly cookie (readable by SPA) and must be
sent back in a header for validation.
"""

import hashlib
import hmac
import secrets

from app.config import get_settings


def generate_csrf_token() -> str:
    """
    Generate a cryptographically secure CSRF token.

    Returns:
        URL-safe random token string (32 bytes = 43 chars base64).
    """
    return secrets.token_urlsafe(32)


def _compute_csrf_signature(token: str, session_id: str) -> str:
    """
    Compute HMAC signature binding CSRF token to session.

    Args:
        token: The CSRF token.
        session_id: The session ID to bind to.

    Returns:
        HMAC-SHA256 signature as hex string.
    """
    settings = get_settings()
    message = f"{token}:{session_id}".encode()
    return hmac.new(
        settings.secret_key.encode(),
        message,
        hashlib.sha256
    ).hexdigest()


def create_signed_csrf_token(session_id: str) -> tuple[str, str]:
    """
    Create a CSRF token bound to a session.

    Args:
        session_id: The session ID to bind the token to.

    Returns:
        Tuple of (token, signature) where token goes to cookie
        and signature is stored server-side.
    """
    token = generate_csrf_token()
    signature = _compute_csrf_signature(token, session_id)
    return token, signature


def validate_csrf_token(
    token: str | None,
    session_id: str,
    stored_signature: str,
) -> bool:
    """
    Validate a CSRF token against a session.

    Args:
        token: The CSRF token from the request header.
        session_id: The session ID from the session cookie.
        stored_signature: The signature stored server-side.

    Returns:
        True if token is valid and bound to session.
    """
    if not token:
        return False

    expected_signature = _compute_csrf_signature(token, session_id)
    return hmac.compare_digest(expected_signature, stored_signature)


def validate_origin(
    origin: str | None,
    referer: str | None,
    allowed_origins: list[str],
) -> bool:
    """
    Validate Origin/Referer headers against allowlist.

    Best-effort validation - returns True if headers are missing
    to avoid breaking legitimate requests (some browsers/proxies strip them).

    Args:
        origin: Origin header value.
        referer: Referer header value.
        allowed_origins: List of allowed origin URLs.

    Returns:
        True if origin is allowed or headers are missing.
    """
    # If no Origin header, try Referer
    check_url = origin
    if not check_url:
        if not referer:
            # No headers to check - allow (best effort)
            return True
        # Extract origin from referer
        # Referer format: https://example.com/path
        try:
            from urllib.parse import urlparse
            parsed = urlparse(referer)
            check_url = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return True  # Can't parse, allow (best effort)

    # Special case for localhost development
    if check_url.startswith(("http://localhost:", "http://127.0.0.1:")):
        return True

    return check_url in allowed_origins
