"""v1 API router.

This module consolidates all v1 API endpoints.
Agents handle the business logic, routers handle HTTP.
"""

from fastapi import APIRouter

from backend.api.v1.status import router as status_router
from backend.api.v1.models import router as models_router
from backend.api.v1.providers import router as providers_router
from backend.api.v1.chat import router as chat_router
from backend.api.v1.conversations import router as conversations_router
from backend.api.v1.voice import router as voice_router
from backend.api.v1.tools import router as tools_router
from backend.api.v1.memory import router as memory_router
from backend.api.v1.ops import router as ops_router
from backend.api.v1.presets import router as presets_router
from backend.api.v1.meta import router as meta_router

router = APIRouter(prefix="/v1")

# Include all v1 routers
router.include_router(meta_router)          # /v1/meta
router.include_router(status_router)        # /v1/status
router.include_router(models_router)        # /v1/models
router.include_router(providers_router)     # /v1/providers
router.include_router(chat_router)         # /v1/chat
router.include_router(conversations_router) # /v1/conversations
router.include_router(voice_router)        # /v1/voice
router.include_router(tools_router)        # /v1/tools
router.include_router(memory_router)       # /v1/memory
router.include_router(ops_router)          # /v1/ops
router.include_router(presets_router)      # /v1/presets
