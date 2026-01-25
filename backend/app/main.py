from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.api.routes_admin import router as admin_router
from backend.app.api.routes_chat import router as chat_router
from backend.app.api.conversations import router as conversations_router
from backend.app.api.health import router as health_router
from backend.app.api.routes_memory import router as memory_router
from backend.app.api.messages import router as messages_router
from backend.app.api.providers import router as providers_router
from backend.app.api.routes_auth import router as auth_router
from backend.app.core.config import settings
from backend.app.core.logging import request_id_var, setup_logging
from backend.app.providers.registry import registry
from backend.app.core.security import cors_kwargs

setup_logging(level=settings.log_level)
logger = logging.getLogger("backend")

_SENSITIVE_KEYS = {
    "password",
    "pass",
    "pwd",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "csrf",
    "authorization",
}


def _redact_value(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if str(key).lower() in _SENSITIVE_KEYS:
                redacted[key] = "***"
            else:
                redacted[key] = _redact_value(item)
        return redacted
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def _safe_headers(request: Request) -> dict:
    allowlist = {
        "user-agent",
        "origin",
        "referer",
        "content-type",
        "x-forwarded-for",
        "x-real-ip",
        "x-request-id",
    }
    headers = {}
    for key, value in request.headers.items():
        if key.lower() in allowlist:
            headers[key] = value
    return headers


async def _safe_body_preview(request: Request, max_bytes: int = 4096) -> str | None:
    try:
        body = await request.body()
    except Exception:
        return None

    if not body:
        return None

    truncated = False
    if len(body) > max_bytes:
        body = body[:max_bytes]
        truncated = True

    content_type = request.headers.get("content-type", "")
    text = None
    if "application/json" in content_type.lower():
        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
            payload = _redact_value(payload)
            text = json.dumps(payload, ensure_ascii=False)
        except Exception:
            text = body.decode("utf-8", errors="replace")
    elif content_type.lower().startswith("text/"):
        text = body.decode("utf-8", errors="replace")

    if text and truncated:
        return f"{text}…(truncated)"
    return text


async def _request_context(request: Request) -> dict:
    context = {
        "method": request.method,
        "path": request.url.path,
        "query": request.url.query,
        "client_ip": request.client.host if request.client else None,
        "headers": _safe_headers(request),
    }
    body_preview = await _safe_body_preview(request)
    if body_preview:
        context["body_preview"] = body_preview
    return context

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Build provider registry on startup."""
    registry.build_registry()
    yield


app = FastAPI(title="OmniPlexity Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    **cors_kwargs(settings.cors_origins, allow_credentials=settings.auth_mode != "bearer"),
)


class OriginLockMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.origin_lock_enabled:
            return await call_next(request)

        # Test-only hook: use X-Test-Client-IP header if present and in test environment
        client_host = request.client.host if request.client else None
        if settings.environment == "test" and "X-Test-Client-IP" in request.headers:
            client_host = request.headers["X-Test-Client-IP"]

        # Allow localhost
        if client_host in ("127.0.0.1", "localhost", "::1"):
            return await call_next(request)

        # Allow OPTIONS for CORS preflight unconditionally
        if request.method == "OPTIONS":
            return await call_next(request)

        # Allow health and version checks for monitoring (no secret required)
        # Normalize path to prevent encoded variant bypass
        normalized_path = unquote(request.url.path)
        allow_without_secret = {"/health", "/version"}
        if normalized_path in allow_without_secret:
            return await call_next(request)

        # Check for tunnel header
        tunnel_secret = request.headers.get("X-Origin-Secret")
        if tunnel_secret == settings.origin_lock_secret:
            return await call_next(request)

        # Reject
        return JSONResponse(
            status_code=403,
            content={
                "code": "ORIGIN_LOCKED",
                "message": "Access denied: origin not allowed",
                "request_id": getattr(request.state, "request_id", "unknown"),
            },
        )


app.add_middleware(OriginLockMiddleware)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Add security headers (safe defaults)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(providers_router)
app.include_router(conversations_router)
app.include_router(messages_router)
app.include_router(memory_router)
app.include_router(chat_router)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        import time
        start_time = time.time()

        response = await call_next(request)

        # Calculate latency
        latency = time.time() - start_time

        # Get route info
        route = getattr(request.scope.get("route"), "path", request.url.path) if hasattr(request.scope, "route") else request.url.path
        method = request.method
        status = response.status_code

        # Log request
        logger.info(
            f"Request completed",
            extra={
                "request_id": getattr(request.state, "request_id", "unknown"),
                "method": method,
                "route": route,
                "status": status,
                "latency_ms": round(latency * 1000, 2),
            }
        )

        return response


app.add_middleware(RequestIDMiddleware)
app.add_middleware(RequestLoggingMiddleware)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", "unknown")
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail)}
    context = await _request_context(request)
    logger.warning(
        "HTTPException",
        extra={
            "request_id": request_id,
            "status_code": exc.status_code,
            "error_code": detail.get("code"),
            "error_message": detail.get("message"),
            **context,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": detail.get("code", "HTTP_ERROR"), "message": detail.get("message", "Request failed"), "request_id": request_id},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", "unknown")
    context = await _request_context(request)
    logger.warning(
        "RequestValidationError",
        extra={
            "request_id": request_id,
            "error_detail": exc.errors(),
            **context,
        },
    )
    return JSONResponse(
        status_code=400,
        content={"code": "VALIDATION_ERROR", "message": "Invalid request", "detail": exc.errors(), "request_id": request_id},
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    context = await _request_context(request)
    logger.error("Unhandled exception", extra={"request_id": request_id, **context}, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An internal error occurred",
            "request_id": request_id,
        },
    )
