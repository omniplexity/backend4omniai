"""
Application middleware for security and observability.

Includes request ID injection, request size limits, and error handling.
"""

import time
import uuid
from collections.abc import Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.csrf import validate_origin
from app.config import get_settings
from app.core.errors import AppError, CSRFError, ErrorCode, ErrorResponse
from app.core.logging import get_logger, request_id_ctx, stream_id_ctx, user_id_ctx

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware to inject request ID and track request context."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with context injection."""
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Set context variables
        request_id_token = request_id_ctx.set(request_id)
        user_id_token = user_id_ctx.set(None)  # Will be set by auth middleware
        stream_id_token = stream_id_ctx.set(None)

        start_time = time.perf_counter()

        try:
            response = await call_next(request)

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            # Log request completion
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "Request completed",
                data={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )

            return response

        finally:
            # Reset context variables
            request_id_ctx.reset(request_id_token)
            user_id_ctx.reset(user_id_token)
            stream_id_ctx.reset(stream_id_token)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce request body size limits."""

    def __init__(self, app: FastAPI, max_bytes: int = 1048576):
        """
        Initialize middleware.

        Args:
            app: FastAPI application
            max_bytes: Maximum request body size in bytes (default 1MB)
        """
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check request size before processing."""
        content_length = request.headers.get("content-length")
        request_id = request_id_ctx.get()

        if content_length and int(content_length) > self.max_bytes:
            logger.warning(
                "Request too large",
                data={
                    "content_length": content_length,
                    "max_bytes": self.max_bytes,
                },
            )
            error_response = ErrorResponse(
                code=ErrorCode.REQUEST_TOO_LARGE,
                message=f"Request body exceeds {self.max_bytes} bytes",
                request_id=request_id,
            )
            return JSONResponse(
                status_code=413,
                content=error_response.to_dict(),
                headers={"X-Request-ID": request_id} if request_id else {},
            )

        return await call_next(request)


class ChatCSRFMiddleware(BaseHTTPMiddleware):
    """Enforce CSRF for /chat routes without triggering FastAPI 422s."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path.startswith("/chat")
        ):
            # Materialize the body so FastAPI reaches parsing before CSRF validation.
            await request.body()
            settings = get_settings()
            origin = request.headers.get("origin")
            referer = request.headers.get("referer")
            if not validate_origin(origin, referer, settings.cors_origins_list):
                raise CSRFError("Invalid origin")

            csrf_header = request.headers.get(settings.csrf_header_name)
            csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
            if not csrf_header or not csrf_cookie:
                raise CSRFError("CSRF token missing")
            if csrf_header != csrf_cookie:
                raise CSRFError("CSRF token mismatch")

            session_token = request.cookies.get(settings.session_cookie_name)
            if not session_token:
                raise CSRFError("Authentication required")

        return await call_next(request)


def setup_exception_handlers(app: FastAPI) -> None:
    """Configure global exception handlers for the application."""
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle validation errors with structured response."""
        request_id = request_id_ctx.get()
        # Extract error details in a clean format
        details = {"errors": exc.errors()}
        error_response = ErrorResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message="Validation error",
            request_id=request_id,
            details=details,
        )
        return JSONResponse(
            status_code=422,
            content=error_response.to_dict(),
            headers={"X-Request-ID": request_id} if request_id else {},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Handle HTTP exceptions with structured response."""
        request_id = request_id_ctx.get()
        # Map status codes to error codes
        code_map = {
            404: ErrorCode.NOT_FOUND,
            405: ErrorCode.METHOD_NOT_ALLOWED,
            401: ErrorCode.UNAUTHORIZED,
            403: ErrorCode.FORBIDDEN,
            429: ErrorCode.RATE_LIMITED,
        }
        error_code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        error_response = ErrorResponse(
            code=error_code,
            message=str(exc.detail) if exc.detail else "HTTP error",
            request_id=request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response.to_dict(),
            headers={"X-Request-ID": request_id} if request_id else {},
        )

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        """Handle application errors with structured response."""
        request_id = request_id_ctx.get()
        logger.warning(
            f"Application error: {exc.message}",
            data={"code": exc.code.value, "details": exc.details},
        )
        error_response = exc.to_response(request_id=request_id)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response.to_dict(),
            headers={"X-Request-ID": request_id} if request_id else {},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle unexpected errors without exposing internals."""
        request_id = request_id_ctx.get()

        # Log full error internally
        logger.error(
            "Unhandled exception",
            exc_info=exc,
            data={"path": request.url.path, "method": request.method},
        )

        # Return safe error to client (no stack trace)
        error_response = ErrorResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message="An unexpected error occurred",
            request_id=request_id,
        )
        return JSONResponse(
            status_code=500,
            content=error_response.to_dict(),
            headers={"X-Request-ID": request_id} if request_id else {},
        )
