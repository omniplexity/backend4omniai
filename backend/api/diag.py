"""
Boot Diagnostics API - Comprehensive System Health & Status.

Provides production-grade diagnostics for monitoring, debugging, and operations.
Designed for both human operators and automated monitoring systems.
"""

import os
import platform
import time
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_optional_user
from backend.config import get_settings
from backend.core.logging import get_logger
from backend.db import get_db
from backend.db.models import Conversation, Message, User

logger = get_logger(__name__)
router = APIRouter(tags=["diagnostics"])

# =============================================================================
# Constants
# =============================================================================

BUILD_VERSION = "0.1.0"
BUILD_DATE = "2024-01"
API_VERSION = "v1"


class Status:
    """Health status constants."""
    OK = "ok"
    DEGRADED = "degraded"
    ERROR = "error"
    UNKNOWN = "unknown"


# =============================================================================
# Helper Functions
# =============================================================================

def format_uptime(seconds: float) -> str:
    """Convert seconds to human-readable uptime string."""
    if seconds <= 0:
        return "just started"

    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


def get_db_type(url: str) -> str:
    """Extract database type from connection URL."""
    if url.startswith("postgresql"):
        return "PostgreSQL"
    elif url.startswith("sqlite"):
        return "SQLite"
    elif url.startswith("mysql"):
        return "MySQL"
    return "Unknown"


def get_public_url(request: Request, settings) -> str:
    """Determine the public URL for this service."""
    public_url = getattr(settings, "public_base_url", "")
    if public_url:
        return public_url

    host = request.headers.get("host", "")
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)

    if host:
        return f"{scheme}://{host}"

    return f"{request.url.scheme}://{request.url.netloc}"


# =============================================================================
# Diagnostic Checks
# =============================================================================

async def check_database(db: DBSession, settings) -> Dict[str, Any]:
    """Comprehensive database health check."""
    result = {
        "status": Status.UNKNOWN,
        "type": get_db_type(settings.database_url),
        "connected": False,
        "latency_ms": None,
        "tables": {},
        "migrations": {"status": Status.UNKNOWN},
    }

    try:
        # Connection test with latency measurement
        start = time.perf_counter()
        db.execute(text("SELECT 1"))
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        result["connected"] = True

        # Table counts
        try:
            result["tables"] = {
                "users": db.query(User).count(),
                "conversations": db.query(Conversation).count(),
                "messages": db.query(Message).count(),
            }
            result["migrations"] = {"status": Status.OK, "tables_exist": True}
            result["status"] = Status.OK
        except Exception:
            result["migrations"] = {
                "status": Status.ERROR,
                "tables_exist": False,
                "hint": "Run: alembic upgrade head",
            }
            result["status"] = Status.DEGRADED

    except Exception as e:
        result["status"] = Status.ERROR
        result["error"] = str(e)
        logger.error(f"Database health check failed: {e}")

    return result


async def check_redis(settings) -> Dict[str, Any]:
    """Check Redis connectivity if configured."""
    redis_url = getattr(settings, "redis_url", "") or os.environ.get("REDIS_URL", "")

    if not redis_url:
        return {"status": Status.UNKNOWN, "configured": False}

    result = {
        "status": Status.UNKNOWN,
        "configured": True,
        "connected": False,
        "latency_ms": None,
    }

    try:
        import redis.asyncio as aioredis

        start = time.perf_counter()
        client = aioredis.from_url(redis_url)
        await client.ping()
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        result["connected"] = True
        result["status"] = Status.OK

        # Get memory info
        info = await client.info("memory")
        result["memory"] = {
            "used_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
            "peak_mb": round(info.get("used_memory_peak", 0) / 1024 / 1024, 2),
        }

        await client.aclose()

    except ImportError:
        result["status"] = Status.UNKNOWN
        result["note"] = "redis package not installed"
    except Exception as e:
        result["status"] = Status.ERROR
        result["error"] = str(e)

    return result


async def check_providers(registry) -> Dict[str, Any]:
    """Comprehensive provider health check with latency and capabilities."""
    if registry is None:
        return {
            "status": Status.UNKNOWN,
            "total": 0,
            "healthy": 0,
            "providers": {},
        }

    providers_detail = {}
    healthy_count = 0

    for name, provider in registry.providers.items():
        provider_info = {
            "status": Status.UNKNOWN,
            "healthy": False,
            "latency_ms": None,
            "models_available": None,
            "capabilities": {},
            "endpoint": None,
        }

        # Get base URL
        if hasattr(provider, "base_url"):
            provider_info["endpoint"] = provider.base_url

        try:
            # Health check with latency
            start = time.perf_counter()
            is_healthy = await provider.healthcheck()
            provider_info["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
            provider_info["healthy"] = is_healthy
            provider_info["status"] = Status.OK if is_healthy else Status.ERROR

            if is_healthy:
                healthy_count += 1

                # Get capabilities
                try:
                    caps = await provider.capabilities()
                    provider_info["capabilities"] = {
                        "streaming": caps.streaming,
                        "function_calling": caps.function_calling,
                        "vision": caps.vision,
                        "embeddings": caps.embeddings,
                        "voice": caps.voice,
                        "tts": caps.tts,
                        "stt": caps.stt,
                    }
                except Exception:
                    pass

                # Get model count
                try:
                    models = await provider.list_models()
                    provider_info["models_available"] = len(models)
                except Exception:
                    pass

        except Exception as e:
            provider_info["status"] = Status.ERROR
            provider_info["error"] = str(e)
            logger.warning(f"Provider {name} health check failed: {e}")

        providers_detail[name] = provider_info

    total = len(registry.providers)
    if healthy_count == total and total > 0:
        overall_status = Status.OK
    elif healthy_count > 0:
        overall_status = Status.DEGRADED
    elif total > 0:
        overall_status = Status.ERROR
    else:
        overall_status = Status.UNKNOWN

    return {
        "status": overall_status,
        "total": total,
        "healthy": healthy_count,
        "default": registry.default_provider,
        "providers": providers_detail,
    }


def check_security(settings, request: Request) -> Dict[str, Any]:
    """Security configuration audit."""
    warnings = []
    recommendations = []

    # Check secret key
    is_default_key = len(settings.secret_key) < 32
    if is_default_key:
        warnings.append("Using default/weak secret key")
        recommendations.append("Set SECRET_KEY environment variable (64+ chars)")

    # Check cookie security
    if not settings.cookie_secure:
        warnings.append("Cookies not marked secure")
        recommendations.append("Enable COOKIE_SECURE=true for HTTPS")

    # Check debug mode
    if settings.debug:
        warnings.append("Debug mode enabled")
        recommendations.append("Set DEBUG=false for production")

    # Check CORS
    cors_origins = settings.cors_origins_list
    if "*" in cors_origins:
        warnings.append("CORS allows all origins")
        recommendations.append("Restrict CORS_ORIGINS to specific domains")

    # Determine auth mode
    if settings.openai_compat_api_key:
        auth_mode = "api_key"
    elif settings.invite_required:
        auth_mode = "invite_only"
    else:
        auth_mode = "open_registration"

    return {
        "status": Status.OK if not warnings else Status.DEGRADED,
        "production_ready": settings.is_production and not warnings,
        "auth_mode": auth_mode,
        "invite_required": settings.invite_required,
        "session": {
            "cookie_name": settings.session_cookie_name,
            "secure": settings.cookie_secure,
            "samesite": settings.cookie_samesite,
            "domain": settings.cookie_domain or "(auto)",
            "ttl_hours": settings.session_ttl_seconds // 3600,
        },
        "cors": {
            "origins": cors_origins,
        },
        "csrf": {
            "header": settings.csrf_header_name,
            "cookie": settings.csrf_cookie_name,
        },
        "warnings": warnings,
        "recommendations": recommendations,
    }


def get_system_info(request: Request, start_time: Optional[datetime]) -> Dict[str, Any]:
    """Gather system and runtime information."""
    uptime_seconds = 0
    if start_time:
        uptime_seconds = (datetime.now(UTC) - start_time).total_seconds()

    return {
        "version": BUILD_VERSION,
        "api_version": API_VERSION,
        "build_date": BUILD_DATE,
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "process": {
            "pid": os.getpid(),
            "uptime_seconds": round(uptime_seconds, 1),
            "uptime": format_uptime(uptime_seconds),
        },
        "time": datetime.now(UTC).isoformat(),
    }


def require_admin_or_debug(settings, current_user: Optional[User]) -> None:
    """Require admin access unless running in debug mode."""
    if settings.debug:
        return
    if not current_user or not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/api/diag")
async def get_diagnostics(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
    db: DBSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    📊 **Comprehensive System Diagnostics**

    Returns detailed health information about all system components:

    - **System**: Version, uptime, Python/platform info
    - **Database**: Connection status, latency, table counts, migration state
    - **Redis**: Cache connection and memory usage
    - **Providers**: AI backend health, latency, capabilities, model counts
    - **Security**: Auth mode, cookie config, CORS, warnings

    **Use Cases:**
    - Debugging deployment issues
    - Monitoring system health
    - Verifying configuration
    - Pre-launch checklist
    """
    settings = get_settings()
    require_admin_or_debug(settings, current_user)
    registry = getattr(request.app.state, "provider_registry", None)
    start_time = getattr(request.app.state, "start_time", None)

    # Run all diagnostic checks
    db_check = await check_database(db, settings)
    redis_check = await check_redis(settings)
    provider_check = await check_providers(registry)
    security_check = check_security(settings, request)
    system_info = get_system_info(request, start_time)

    # Determine overall status
    statuses = [db_check["status"], provider_check["status"]]
    if redis_check.get("configured"):
        statuses.append(redis_check["status"])

    if Status.ERROR in statuses:
        overall_status = Status.ERROR
    elif Status.DEGRADED in statuses or security_check["warnings"]:
        overall_status = Status.DEGRADED
    elif Status.UNKNOWN in statuses:
        overall_status = Status.DEGRADED
    else:
        overall_status = Status.OK

    # Status emoji for quick visual
    status_emoji = {"ok": "✅", "degraded": "⚠️", "error": "❌", "unknown": "❓"}

    # User context
    if current_user:
        user_info = {
            "authenticated": True,
            "id": current_user.id,
            "username": current_user.username,
            "is_admin": current_user.is_admin,
        }
    else:
        user_info = {"authenticated": False}

    return {
        "status": overall_status,
        "status_emoji": status_emoji.get(overall_status, "❓"),
        "timestamp": datetime.now(UTC).isoformat(),
        "public_url": get_public_url(request, settings),
        "system": system_info,
        "database": db_check,
        "redis": redis_check,
        "providers": provider_check,
        "security": security_check,
        "user": user_info,
    }


@router.get("/api/diag/lite")
async def get_diagnostics_lite(
    request: Request,
    db: DBSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    ⚡ **Lightweight Health Check**

    Fast health probe for:
    - Kubernetes liveness/readiness probes
    - Load balancer health checks
    - Uptime monitoring services

    Returns minimal payload with sub-100ms response time.
    """
    registry = getattr(request.app.state, "provider_registry", None)

    # Quick database check
    db_ok = False
    db_latency = None
    try:
        start = time.perf_counter()
        db.execute(text("SELECT 1"))
        db_latency = round((time.perf_counter() - start) * 1000, 2)
        db_ok = True
    except Exception:
        pass

    # Quick provider check
    providers_ok = 0
    providers_total = 0
    if registry:
        providers_total = len(registry.providers)
        for provider in registry.providers.values():
            try:
                if await provider.healthcheck():
                    providers_ok += 1
            except Exception:
                pass

    # Overall health
    is_healthy = db_ok and (providers_total == 0 or providers_ok > 0)

    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "emoji": "✅" if is_healthy else "❌",
        "checks": {
            "database": {"ok": db_ok, "latency_ms": db_latency},
            "providers": {"ok": providers_ok, "total": providers_total},
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/api/diag/providers")
async def get_provider_diagnostics(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
) -> Dict[str, Any]:
    """
    🤖 **Provider Diagnostics**

    Detailed information about each configured AI provider:
    - Health status and latency
    - Available models (up to 20)
    - Capabilities (streaming, vision, voice, etc.)
    - Endpoint URLs
    """
    settings = get_settings()
    require_admin_or_debug(settings, current_user)
    registry = getattr(request.app.state, "provider_registry", None)
    provider_check = await check_providers(registry)

    # Add model listings for healthy providers
    if registry:
        for name, provider in registry.providers.items():
            if provider_check["providers"].get(name, {}).get("healthy"):
                try:
                    models = await provider.list_models()
                    provider_check["providers"][name]["models"] = [
                        {"id": m.id, "name": m.name}
                        for m in models[:20]
                    ]
                    if len(models) > 20:
                        provider_check["providers"][name]["models_truncated"] = len(models)
                except Exception:
                    pass

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        **provider_check,
    }


@router.get("/api/diag/database")
async def get_database_diagnostics(
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
) -> Dict[str, Any]:
    """
    🗄️ **Database Diagnostics**

    Detailed database health information:
    - Connection status and latency
    - Table statistics
    - Migration state
    - Connection string (password masked)
    """
    settings = get_settings()
    require_admin_or_debug(settings, current_user)
    db_check = await check_database(db, settings)

    # Add masked connection info
    db_url = settings.database_url
    if "@" in db_url:
        parts = db_url.split("@")
        prefix = parts[0].rsplit(":", 1)[0]
        db_check["connection"] = f"{prefix}:***@{parts[1]}"
    else:
        db_check["connection"] = db_url

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        **db_check,
    }


@router.get("/api/diag/security")
async def get_security_diagnostics(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
) -> Dict[str, Any]:
    """
    🔒 **Security Audit**

    Security configuration review:
    - Authentication mode
    - Session/cookie settings
    - CORS configuration
    - Warnings and recommendations

    Sensitive values are always masked.
    """
    settings = get_settings()
    require_admin_or_debug(settings, current_user)
    security_check = check_security(settings, request)

    # Add request context
    security_check["request"] = {
        "ip": request.headers.get("x-forwarded-for",
              request.client.host if request.client else "unknown"),
        "user_agent": request.headers.get("user-agent", "unknown")[:100],
        "scheme": request.headers.get("x-forwarded-proto", request.url.scheme),
        "host": request.headers.get("host", request.url.netloc),
    }

    if current_user:
        security_check["current_user"] = {
            "id": current_user.id,
            "username": current_user.username,
            "is_admin": current_user.is_admin,
        }

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        **security_check,
    }


@router.get("/api/diag/health-summary")
async def get_health_summary(
    request: Request,
    db: DBSession = Depends(get_db),
) -> Dict[str, Any]:
    """Alias for /api/diag/lite - backwards compatibility."""
    return await get_diagnostics_lite(request, db)


@router.get("/api/diag/connections")
async def get_connection_status(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
) -> Dict[str, Any]:
    """
    🌐 **Connection Details**

    Request and connection information:
    - Client IP and user agent
    - Request headers (sensitive ones filtered)
    - Server process info and uptime
    """
    settings = get_settings()
    require_admin_or_debug(settings, current_user)
    start_time = getattr(request.app.state, "start_time", None)

    # Filter sensitive headers
    safe_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("authorization", "cookie", "x-api-key", "x-csrf-token")
    }

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "client": {
            "ip": request.headers.get("x-forwarded-for",
                  request.client.host if request.client else "unknown"),
            "user_agent": request.headers.get("user-agent", "unknown"),
        },
        "request": {
            "scheme": request.headers.get("x-forwarded-proto", request.url.scheme),
            "host": request.headers.get("host", request.url.netloc),
            "path": str(request.url.path),
            "method": request.method,
        },
        "server": {
            "pid": os.getpid(),
            "started": start_time.isoformat() if start_time else None,
            "uptime": format_uptime(
                (datetime.now(UTC) - start_time).total_seconds()
            ) if start_time else "unknown",
        },
        "headers": safe_headers,
    }
