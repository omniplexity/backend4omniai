"""Custom middleware for OmniAI backend."""

import secrets
import time
from collections import deque
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.core.logging import get_logger, request_context

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware to inject request context for logging."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with context."""
        request_id = request.headers.get("X-Request-ID") or secrets.token_hex(8)
        start_time = time.perf_counter()

        # Set context for logging
        ctx = {
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
        }
        token = request_context.set(ctx)

        try:
            response = await call_next(request)

            # Log request completion
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"{request.method} {request.url.path} -> {response.status_code}",
                data={"duration_ms": round(duration_ms, 2)},
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            return response

        finally:
            request_context.reset(token)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to limit request body size."""

    def __init__(self, app, max_bytes: int = 1048576, voice_max_bytes: int | None = None):
        """Initialize with max size in bytes."""
        super().__init__(app)
        self.max_bytes = max_bytes
        self.voice_max_bytes = voice_max_bytes or max_bytes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check request size before processing."""
        content_length = request.headers.get("content-length")
        limit = self.max_bytes
        if request.url.path.startswith("/v1/voice") or request.url.path.startswith("/api/voice"):
            limit = self.voice_max_bytes

        if content_length and int(content_length) > limit:
            logger.warning(
                f"Request too large: {content_length} bytes",
                data={"max_bytes": limit},
            )
            return Response(
                content='{"detail": "Request body too large", "error": {"code": "E4130", "message": "Request body too large"}}',
                status_code=413,
                media_type="application/json",
            )

        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiting middleware."""

    EXEMPT_PATHS = {"/health", "/healthz", "/readyz", "/api/diag/lite"}

    def __init__(
        self,
        app,
        ip_requests_per_minute: int = 60,
        user_requests_per_minute: int = 60,
    ):
        """Initialize rate limiter with per-IP and per-user RPM.

        Per-user limits require a valid session cookie; they are enforced
        in addition to per-IP limits.
        """
        super().__init__(app)
        self.ip_requests_per_minute = max(0, int(ip_requests_per_minute))
        self.user_requests_per_minute = max(0, int(user_requests_per_minute))
        self.window_seconds = 60
        self._ip_buckets: dict[str, deque[float]] = {}
        self._user_buckets: dict[str, deque[float]] = {}

    def _allow(self, buckets: dict[str, deque[float]], key: str, limit: int, now: float) -> bool:
        if limit <= 0:
            return True

        bucket = buckets.get(key)
        if bucket is None:
            bucket = deque()
            buckets[key] = bucket

        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= limit:
            return False

        bucket.append(now)
        return True

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Apply rate limiting to incoming requests."""
        if self.ip_requests_per_minute <= 0 and self.user_requests_per_minute <= 0:
            return await call_next(request)

        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Determine client IP (respect X-Forwarded-For when present)
        forwarded_for = request.headers.get("x-forwarded-for", "")
        client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else None
        if not client_ip and request.client:
            client_ip = request.client.host
        client_ip = client_ip or "unknown"

        now = time.monotonic()

        # Per-IP limit (always enforce if enabled)
        if not self._allow(self._ip_buckets, client_ip, self.ip_requests_per_minute, now):
            logger.warning(
                "Rate limit exceeded",
                data={"scope": "ip", "ip": client_ip, "rpm": self.ip_requests_per_minute},
            )
            return Response(
                content='{"detail": "Rate limit exceeded", "error": {"code": "E1005", "message": "Rate limit exceeded"}}',
                status_code=429,
                media_type="application/json",
            )

        # Per-user limit (only if session is valid)
        if self.user_requests_per_minute > 0:
            try:
                from backend.config import get_settings
                from backend.auth.session import validate_session
                from backend.db.database import get_session_local

                settings = get_settings()
                session_cookie = request.cookies.get(settings.session_cookie_name)
                if session_cookie:
                    SessionLocal = get_session_local()
                    db = SessionLocal()
                    try:
                        session = validate_session(db, session_cookie)
                    finally:
                        db.close()

                    if session:
                        user_key = session.user_id
                        if not self._allow(
                            self._user_buckets,
                            user_key,
                            self.user_requests_per_minute,
                            now,
                        ):
                            logger.warning(
                                "Rate limit exceeded",
                                data={
                                    "scope": "user",
                                    "user_id": user_key,
                                    "rpm": self.user_requests_per_minute,
                                },
                            )
                            return Response(
                                content='{"detail": "Rate limit exceeded", "error": {"code": "E1006", "message": "Rate limit exceeded"}}',
                                status_code=429,
                                media_type="application/json",
                            )
            except Exception:
                # Fail open for user limiting; IP limiting still applies.
                pass

        return await call_next(request)


class ChatCSRFMiddleware(BaseHTTPMiddleware):
    """CSRF protection middleware for chat endpoints."""

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
    EXEMPT_PATHS = {"/health", "/readyz", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Validate CSRF token for state-changing requests."""
        from backend.config import get_settings

        # Skip CSRF check for safe methods and exempt paths
        if request.method in self.SAFE_METHODS:
            return await call_next(request)

        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        settings = get_settings()

        # For API endpoints, check CSRF header matches cookie when session cookie is present
        if request.url.path.startswith(("/api/", "/v1/")):
            session_cookie = request.cookies.get(settings.session_cookie_name)
            if not session_cookie:
                return await call_next(request)

            # Validate session before enforcing CSRF
            session = None
            db = None
            try:
                from backend.auth.session import validate_session
                from backend.db.database import get_session_local

                SessionLocal = get_session_local()
                db = SessionLocal()
                session = validate_session(db, session_cookie)
            finally:
                if db is not None:
                    db.close()

            if not session:
                return await call_next(request)

            csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
            csrf_header = request.headers.get(settings.csrf_header_name)

            # If session cookie exists, CSRF cookie and header must exist and match
            if (
                not csrf_cookie
                or not csrf_header
                or csrf_cookie != csrf_header
                or csrf_cookie != session.csrf_token
            ):
                logger.warning(
                    "CSRF validation failed",
                    data={"path": request.url.path},
                )
                return Response(
                    content='{"detail": "CSRF validation failed", "error": {"code": "E2002", "message": "CSRF validation failed"}}',
                    status_code=403,
                    media_type="application/json",
                )

        return await call_next(request)
