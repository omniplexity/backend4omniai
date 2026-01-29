"""API routers."""

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.providers import router as providers_router

__all__ = [
    "admin_router",
    "auth_router",
    "chat_router",
    "health_router",
    "providers_router",
]
