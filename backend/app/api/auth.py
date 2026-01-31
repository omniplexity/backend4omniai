"""
Authentication API endpoints.

Handles user registration, login, logout, and session management.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth import (
    RequireAuth,
    ValidateCSRF,
    create_session,
    delete_session,
    hash_password,
    verify_password,
)
from app.auth.csrf import create_signed_csrf_token
from app.config import get_settings
from app.core import (
    EmailTakenError,
    InvalidCredentialsError,
    InviteExpiredError,
    InviteInvalidError,
    InviteRequiredError,
    UsernameTakenError,
    ValidationError,
)
from app.db import get_db
from app.db.repositories import (
    create_user,
    email_exists,
    get_user_by_username_or_email,
    log_login,
    log_logout,
    log_register,
    log_session_create,
    update_last_login,
    use_invite,
    username_exists,
    validate_invite,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# Request/Response schemas
class RegisterRequest(BaseModel):
    """Registration request body."""

    username: str = Field(
        ..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    password: str = Field(..., min_length=8, max_length=128)
    email: EmailStr | None = None
    invite_code: str | None = None


class LoginRequest(BaseModel):
    """Login request body."""

    username: str = Field(..., min_length=1)  # Can be username or email
    password: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    """User info response."""

    id: str
    username: str
    email: str | None
    role: str
    status: str


class CSRFResponse(BaseModel):
    """CSRF token response."""

    csrf_token: str


def get_client_ip(request: Request) -> str | None:
    """Extract client IP address from request."""
    # Check X-Forwarded-For header first (for reverse proxies)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    # Fall back to direct client IP
    if request.client:
        return request.client.host
    return None


def _format_samesite(value: str | None) -> str | None:
    if not value:
        return None
    lower = value.lower()
    if lower == "none":
        return "None"
    if lower == "lax":
        return "Lax"
    if lower == "strict":
        return "Strict"
    return value


def _set_cookie_with_optional_partition(
    response: Response,
    *,
    key: str,
    value: str,
    httponly: bool,
    secure: bool,
    samesite: str | None,
    domain: str | None,
    max_age: int | None,
    partitioned: bool,
) -> None:
    if not partitioned:
        response.set_cookie(
            key=key,
            value=value,
            httponly=httponly,
            secure=secure,
            samesite=samesite,
            domain=domain or None,
            max_age=max_age,
        )
        return

    cookie = f"{key}={value}; Path=/"
    if domain:
        cookie += f"; Domain={domain}"
    if max_age is not None:
        cookie += f"; Max-Age={max_age}"
    if secure:
        cookie += "; Secure"
    if httponly:
        cookie += "; HttpOnly"
    if samesite:
        cookie += f"; SameSite={samesite}"
    cookie += "; Partitioned"
    response.headers.append("Set-Cookie", cookie)


def _delete_cookie_with_optional_partition(
    response: Response,
    *,
    key: str,
    domain: str | None,
    partitioned: bool,
) -> None:
    if not partitioned:
        response.delete_cookie(
            key=key,
            domain=domain or None,
        )
        return

    cookie = f"{key}=; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT"
    if domain:
        cookie += f"; Domain={domain}"
    cookie += "; Secure; SameSite=None; Partitioned"
    response.headers.append("Set-Cookie", cookie)


def set_session_cookie(response: Response, token: str) -> None:
    """Set session cookie on response."""
    settings = get_settings()
    secure = settings.cookie_secure if settings.is_production else False
    samesite = _format_samesite(settings.cookie_samesite)
    partitioned = samesite == "None" and secure
    _set_cookie_with_optional_partition(
        response,
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        domain=settings.cookie_domain or None,
        max_age=settings.session_ttl_seconds,
        partitioned=partitioned,
    )


def set_csrf_cookie(response: Response, token: str) -> None:
    """Set CSRF cookie on response (readable by JS)."""
    settings = get_settings()
    secure = settings.cookie_secure if settings.is_production else False
    samesite = _format_samesite(settings.cookie_samesite)
    partitioned = samesite == "None" and secure
    _set_cookie_with_optional_partition(
        response,
        key=settings.csrf_cookie_name,
        value=token,
        httponly=False,  # Must be readable by JS
        secure=secure,
        samesite=samesite,
        domain=settings.cookie_domain or None,
        max_age=settings.session_ttl_seconds,
        partitioned=partitioned,
    )


def clear_auth_cookies(response: Response) -> None:
    """Clear session and CSRF cookies."""
    settings = get_settings()
    samesite = _format_samesite(settings.cookie_samesite)
    partitioned = samesite == "None" and settings.cookie_secure
    _delete_cookie_with_optional_partition(
        response,
        key=settings.session_cookie_name,
        domain=settings.cookie_domain or None,
        partitioned=partitioned,
    )
    _delete_cookie_with_optional_partition(
        response,
        key=settings.csrf_cookie_name,
        domain=settings.cookie_domain or None,
        partitioned=partitioned,
    )


@router.post("/register")
async def register(
    request: Request,
    response: Response,
    body: RegisterRequest,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """
    Register a new user account.

    Requires a valid invite code if INVITE_REQUIRED is true.
    """
    settings = get_settings()
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("user-agent")

    # Validate invite code if required
    invite = None
    if settings.invite_required:
        if not body.invite_code:
            raise InviteRequiredError()

        invite = validate_invite(db, body.invite_code)
        if not invite:
            # Check if it exists but is invalid
            from app.db.repositories import get_invite_by_code

            existing = get_invite_by_code(db, body.invite_code)
            if existing:
                raise InviteExpiredError("Invite code expired or already used")
            raise InviteInvalidError()

    # Check username availability
    if username_exists(db, body.username):
        raise UsernameTakenError()

    # Check email availability
    if body.email and email_exists(db, body.email):
        raise EmailTakenError()

    # Hash password
    password_hash = hash_password(body.password)

    # Create user
    user = create_user(
        db,
        username=body.username,
        password_hash=password_hash,
        email=body.email,
        role="user",
        status="active",
    )

    # Mark invite as used
    if invite:
        use_invite(db, invite, user.id)

    # Create session
    session_data = create_session(
        db, user, ip_address=ip_address, user_agent=user_agent
    )

    # Set cookies
    set_session_cookie(response, session_data.token)
    set_csrf_cookie(response, session_data.csrf_token)

    # Log events
    log_register(
        db,
        user_id=user.id,
        username=user.username,
        invite_code=body.invite_code,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    log_session_create(
        db,
        user_id=user.id,
        session_id=session_data.session_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return {
        "user": UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            status=user.status,
        ).model_dump(),
        "csrf_token": session_data.csrf_token,
    }


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """
    Log in with username/email and password.

    Returns user info and sets session cookies.
    """
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("user-agent")

    # Find user
    user = get_user_by_username_or_email(db, body.username)
    if not user:
        # Log failed attempt (user not found)
        log_login(db, user_id="", ip_address=ip_address, user_agent=user_agent, success=False)
        raise InvalidCredentialsError()

    # Verify password
    if not verify_password(body.password, user.password_hash):
        # Log failed attempt (wrong password)
        log_login(db, user_id=user.id, ip_address=ip_address, user_agent=user_agent, success=False)
        raise InvalidCredentialsError()

    # Check user status
    if user.status == "disabled":
        from app.core import AccountDisabledError

        raise AccountDisabledError()

    if user.status != "active":
        raise ValidationError("Account not active", {"status": user.status})

    # Create session
    session_data = create_session(
        db, user, ip_address=ip_address, user_agent=user_agent
    )

    # Update last login
    update_last_login(db, user)

    # Set cookies
    set_session_cookie(response, session_data.token)
    set_csrf_cookie(response, session_data.csrf_token)

    # Log events
    log_login(db, user_id=user.id, ip_address=ip_address, user_agent=user_agent, success=True)
    log_session_create(
        db,
        user_id=user.id,
        session_id=session_data.session_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return {
        "user": UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            status=user.status,
        ).model_dump(),
        "csrf_token": session_data.csrf_token,
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    auth: RequireAuth,
    _csrf: ValidateCSRF,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """
    Log out and invalidate current session.

    Requires authentication (valid session).
    """
    user, session = auth
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("user-agent")

    # Delete session
    delete_session(db, session.id)

    # Clear cookies
    clear_auth_cookies(response)

    # Log event
    log_logout(
        db,
        user_id=user.id,
        session_id=session.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return {"status": "logged_out"}


@router.get("/me")
async def get_current_user_info(auth: RequireAuth) -> dict[str, Any]:
    """
    Get current authenticated user info.

    Requires authentication (valid session).
    """
    user, _ = auth

    return {
        "user": UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            status=user.status,
        ).model_dump()
    }


@router.get("/csrf")
async def get_csrf_token(
    response: Response,
    auth: RequireAuth,
) -> CSRFResponse:
    """
    Get a fresh CSRF token.

    Returns the token in both the response body and a cookie.
    Requires authentication (valid session).
    """
    _, session = auth

    # Generate new CSRF token bound to session
    csrf_token, _ = create_signed_csrf_token(session.id)

    # Set cookie
    set_csrf_cookie(response, csrf_token)

    return CSRFResponse(csrf_token=csrf_token)
