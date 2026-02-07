"""API routers."""

from backend.api.admin import router as admin_router
from backend.api.auth import router as auth_router
from backend.api.chat import router as chat_router
from backend.api.diag import router as diag_router
from backend.api.health import router as health_router
from backend.api.providers import router as providers_router
from backend.api.voice import router as voice_router
from backend.api.tools import router as tools_router
from backend.api.media import router as media_router
from backend.api.memory import router as memory_router
from backend.api.knowledge import router as knowledge_router
from backend.api.plan import router as plan_router
from backend.api.projects import router as projects_router
from backend.api.context_blocks import router as context_blocks_router
from backend.api.artifacts import router as artifacts_router
from backend.api.workflows import router as workflows_router

__all__ = [
    "admin_router",
    "auth_router",
    "chat_router",
    "diag_router",
    "health_router",
    "providers_router",
    "voice_router",
    "tools_router",
    "media_router",
    "memory_router",
    "knowledge_router",
    "plan_router",
    "projects_router",
    "context_blocks_router",
    "artifacts_router",
    "workflows_router",
]
