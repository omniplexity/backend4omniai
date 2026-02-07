"""Exception handlers for FastAPI application."""

from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.core.logging import get_logger, request_context

logger = get_logger(__name__)


class OmniAIException(Exception):
    """Base exception for OmniAI application."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        code: str = "E5000",
        details: dict = None,
    ):
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}
        super().__init__(message)


class AuthenticationError(OmniAIException):
    """Authentication failed."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, status_code=status.HTTP_401_UNAUTHORIZED, code="E2000")


class AuthorizationError(OmniAIException):
    """Authorization failed."""

    def __init__(self, message: str = "Access denied"):
        super().__init__(message, status_code=status.HTTP_403_FORBIDDEN, code="E2001")


class NotFoundError(OmniAIException):
    """Resource not found."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=status.HTTP_404_NOT_FOUND, code="E4040")


class ProviderError(OmniAIException):
    """AI provider error."""

    def __init__(self, message: str, provider: str = None):
        super().__init__(
            message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="E3000",
            details={"provider": provider} if provider else {},
        )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers with FastAPI app."""

    @app.exception_handler(OmniAIException)
    async def omniai_exception_handler(
        request: Request, exc: OmniAIException
    ) -> JSONResponse:
        """Handle OmniAI-specific exceptions."""
        logger.error(
            f"OmniAI error: {exc.message}",
            data={"status_code": exc.status_code, "details": exc.details},
        )
        request_id = request_context.get().get("request_id") if request_context.get() else None
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.message,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": request_id,
                },
                **exc.details,
            },
        )

    @app.exception_handler(ValidationError)
    async def validation_exception_handler(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors."""
        logger.warning(
            "Validation error",
            data={"errors": exc.errors()},
        )
        request_id = request_context.get().get("request_id") if request_context.get() else None
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Validation error",
                "errors": exc.errors(),
                "error": {
                    "code": "E4220",
                    "message": "Validation error",
                    "request_id": request_id,
                },
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle unexpected exceptions."""
        logger.error(
            f"Unhandled exception: {type(exc).__name__}: {exc}",
            exc_info=True,
        )
        request_id = request_context.get().get("request_id") if request_context.get() else None
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error",
                "error": {
                    "code": "E5000",
                    "message": "Internal server error",
                    "request_id": request_id,
                },
            },
        )
    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        request_id = request_context.get().get("request_id") if request_context.get() else None
        code = f"E{exc.status_code}0"
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "error": {
                    "code": code,
                    "message": exc.detail,
                    "request_id": request_id,
                },
            },
            headers=exc.headers,
        )
