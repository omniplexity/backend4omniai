"""
Structured error handling with stable error codes.

No stack traces are exposed to clients. All errors are mapped to
stable, documented error codes for reliable client handling.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Stable error codes for API responses."""

    # General errors (1xxx)
    INTERNAL_ERROR = "E1000"
    VALIDATION_ERROR = "E1001"
    NOT_FOUND = "E1002"
    METHOD_NOT_ALLOWED = "E1003"
    REQUEST_TOO_LARGE = "E1004"
    RATE_LIMITED = "E1005"

    # Authentication errors (2xxx)
    UNAUTHORIZED = "E2000"
    INVALID_CREDENTIALS = "E2001"
    SESSION_EXPIRED = "E2002"
    CSRF_FAILED = "E2003"
    INVITE_REQUIRED = "E2004"
    INVITE_INVALID = "E2005"
    INVITE_EXPIRED = "E2006"
    ACCOUNT_DISABLED = "E2007"
    USERNAME_TAKEN = "E2008"
    EMAIL_TAKEN = "E2009"
    QUOTA_EXCEEDED = "E2010"

    # Authorization errors (3xxx)
    FORBIDDEN = "E3000"
    INSUFFICIENT_PERMISSIONS = "E3001"

    # Provider errors (4xxx)
    PROVIDER_UNAVAILABLE = "E4000"
    PROVIDER_ERROR = "E4001"
    MODEL_NOT_FOUND = "E4002"
    STREAMING_ERROR = "E4003"
    PROVIDER_BAD_RESPONSE = "E4004"
    PROVIDER_AUTH_FAILED = "E4005"

    # Resource errors (5xxx)
    CONVERSATION_NOT_FOUND = "E5000"
    MESSAGE_NOT_FOUND = "E5001"
    USER_NOT_FOUND = "E5002"


@dataclass(frozen=True)
class ErrorResponse:
    """Structured error response for API.

    Format: {error: {code, message, request_id, details?}}
    """

    code: ErrorCode
    message: str
    request_id: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON response."""
        error: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.request_id:
            error["request_id"] = self.request_id
        if self.details:
            error["details"] = self.details
        return {"error": error}


class AppError(Exception):
    """Base application error with structured error detail."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)

    def to_response(self, request_id: str | None = None) -> ErrorResponse:
        """Create error response with request ID."""
        return ErrorResponse(
            code=self.code,
            message=self.message,
            request_id=request_id,
            details=self.details,
        )


# Convenience error classes
class ValidationError(AppError):
    """Validation error (400)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(ErrorCode.VALIDATION_ERROR, message, 400, details)


class NotFoundError(AppError):
    """Resource not found (404)."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(ErrorCode.NOT_FOUND, message, 404)


class UnauthorizedError(AppError):
    """Authentication required (401)."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(ErrorCode.UNAUTHORIZED, message, 401)


class ForbiddenError(AppError):
    """Access denied (403)."""

    def __init__(self, message: str = "Access denied"):
        super().__init__(ErrorCode.FORBIDDEN, message, 403)


class RateLimitError(AppError):
    """Rate limit exceeded (429)."""

    def __init__(self, message: str = "Rate limit exceeded", details: dict[str, Any] | None = None):
        super().__init__(ErrorCode.RATE_LIMITED, message, 429, details)


class ProviderError(AppError):
    """Provider error (502)."""

    def __init__(
        self, message: str = "Provider error", details: dict[str, Any] | None = None
    ):
        super().__init__(ErrorCode.PROVIDER_ERROR, message, 502, details)


class ProviderUnavailableError(AppError):
    """Provider unavailable (503)."""

    def __init__(
        self, message: str = "Provider unavailable", details: dict[str, Any] | None = None
    ):
        super().__init__(ErrorCode.PROVIDER_UNAVAILABLE, message, 503, details)


class ProviderBadResponseError(AppError):
    """Provider returned malformed response (502)."""

    def __init__(
        self, message: str = "Provider returned invalid response", details: dict[str, Any] | None = None
    ):
        super().__init__(ErrorCode.PROVIDER_BAD_RESPONSE, message, 502, details)


class ProviderAuthError(AppError):
    """Provider authentication failed (401/403)."""

    def __init__(
        self,
        message: str = "Provider authentication failed",
        status_code: int = 401,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(ErrorCode.PROVIDER_AUTH_FAILED, message, status_code, details)


class InvalidCredentialsError(AppError):
    """Invalid credentials (401)."""

    def __init__(self, message: str = "Invalid username or password"):
        super().__init__(ErrorCode.INVALID_CREDENTIALS, message, 401)


class SessionExpiredError(AppError):
    """Session expired (401)."""

    def __init__(self, message: str = "Session expired"):
        super().__init__(ErrorCode.SESSION_EXPIRED, message, 401)


class CSRFError(AppError):
    """CSRF validation failed (403)."""

    def __init__(self, message: str = "CSRF validation failed"):
        super().__init__(ErrorCode.CSRF_FAILED, message, 403)


class InviteRequiredError(AppError):
    """Invite code required (400)."""

    def __init__(self, message: str = "Invite code required for registration"):
        super().__init__(ErrorCode.INVITE_REQUIRED, message, 400)


class InviteInvalidError(AppError):
    """Invite code invalid (400)."""

    def __init__(self, message: str = "Invalid invite code"):
        super().__init__(ErrorCode.INVITE_INVALID, message, 400)


class InviteExpiredError(AppError):
    """Invite code expired (400)."""

    def __init__(self, message: str = "Invite code has expired"):
        super().__init__(ErrorCode.INVITE_EXPIRED, message, 400)


class AccountDisabledError(AppError):
    """Account disabled (403)."""

    def __init__(self, message: str = "Account is disabled"):
        super().__init__(ErrorCode.ACCOUNT_DISABLED, message, 403)


class QuotaExceededError(AppError):
    """Quota exceeded (429)."""

    def __init__(self, message: str = "Quota exceeded", details: dict[str, Any] | None = None):
        super().__init__(ErrorCode.QUOTA_EXCEEDED, message, 429, details)


class UsernameTakenError(AppError):
    """Username already taken (409)."""

    def __init__(self, message: str = "Username already taken"):
        super().__init__(ErrorCode.USERNAME_TAKEN, message, 409)


class EmailTakenError(AppError):
    """Email already taken (409)."""

    def __init__(self, message: str = "Email already registered"):
        super().__init__(ErrorCode.EMAIL_TAKEN, message, 409)


class ModelNotFoundError(AppError):
    """Requested model not found (404)."""

    def __init__(self, message: str = "Model not found", details: dict[str, Any] | None = None):
        super().__init__(ErrorCode.MODEL_NOT_FOUND, message, 404, details)
