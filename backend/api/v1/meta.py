"""v1 meta endpoint.

Single source of truth for frontend boot + feature gating.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request

from backend.auth.dependencies import get_optional_user
from backend.config import get_settings
from backend.db.models import User
from backend.services.capabilities_service import compute_service_capabilities
from backend.services.tool_capabilities_service import get_tool_capabilities

router = APIRouter()


def _uptime_seconds(request: Request) -> Optional[int]:
    start_time = getattr(request.app.state, "start_time", None)
    if not start_time:
        return None
    now = datetime.now(UTC)
    return int((now - start_time).total_seconds())


def _feature_entry(*, supported: bool, permitted: bool, reason: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "supported": bool(supported),
        "permitted": bool(permitted),
        "reason": reason,
        "details": details or {},
    }


@router.get("/meta")
async def get_meta(
    request: Request,
    current_user: Optional[User] = Depends(get_optional_user),
) -> Dict[str, Any]:
    settings = get_settings()
    authenticated = current_user is not None

    registry = getattr(request.app.state, "provider_registry", None)
    capabilities = await compute_service_capabilities(registry)

    # Tool subsystem details (kept separate from the high-level capabilities booleans).
    tools_caps = get_tool_capabilities()
    mcp_details = {
        "configured_servers": 0,
        "supports_receipts": bool(tools_caps.get("supports_receipts")),
        "supports_favorites": bool(tools_caps.get("supports_favorites")),
        "supports_mcp": bool(tools_caps.get("supports_mcp")),
        "supports_connectors": bool(tools_caps.get("supports_connectors")),
    }

    # Auth is required for core backend features in this build.
    auth_required = True

    user_payload: Optional[Dict[str, Any]] = None
    if current_user is not None:
        user_payload = {
            "id": current_user.id,
            "email": current_user.email,
            "username": current_user.username,
            "is_admin": bool(current_user.is_admin),
        }

    # Authoritative server-backed feature flags the frontend may request.
    features: Dict[str, Any] = {}

    def set_feature(feature_id: str, *, supported: bool, permitted: bool, reason_if_disabled: str, details: Optional[Dict[str, Any]] = None):
        reason = "ok" if (supported and permitted) else reason_if_disabled
        features[feature_id] = _feature_entry(supported=supported, permitted=permitted, reason=reason, details=details)

    # Auth-gated features (permitted iff authenticated). Support is based on implementation availability.
    def auth_gate(supported: bool) -> tuple[bool, bool, str]:
        if not supported:
            return False, False, "not_supported"
        if not authenticated:
            return True, False, "login_required"
        return True, True, "ok"

    # chat_sse_v2: v1 run-based streaming is implemented.
    supported, permitted, reason = auth_gate(True)
    set_feature("chat_sse_v2", supported=supported, permitted=permitted, reason_if_disabled=reason)

    # voice/vision/tools/connectors/mcp/media_generation
    supported, permitted, reason = auth_gate(bool(capabilities.get("voice", {}).get("available")))
    set_feature("voice", supported=supported, permitted=permitted, reason_if_disabled=reason, details=capabilities.get("voice", {}))

    supported, permitted, reason = auth_gate(bool(capabilities.get("vision", {}).get("image_input")))
    set_feature("vision", supported=supported, permitted=permitted, reason_if_disabled=reason, details=capabilities.get("vision", {}))

    supported, permitted, reason = auth_gate(True)
    set_feature("tools", supported=supported, permitted=permitted, reason_if_disabled=reason, details=tools_caps)

    supported, permitted, reason = auth_gate(bool(capabilities.get("tools", {}).get("connectors")))
    set_feature("connectors", supported=supported, permitted=permitted, reason_if_disabled=reason, details={"configured_connectors": 0})

    supported, permitted, reason = auth_gate(bool(capabilities.get("tools", {}).get("mcp")))
    set_feature("mcp", supported=supported, permitted=permitted, reason_if_disabled=reason, details=mcp_details)

    supported, permitted, reason = auth_gate(bool(capabilities.get("media", {}).get("img2img")) or bool(capabilities.get("media", {}).get("img2video")))
    set_feature("media_generation", supported=supported, permitted=permitted, reason_if_disabled=reason, details=capabilities.get("media", {}))

    # knowledge/citations
    supported, permitted, reason = auth_gate(True)
    set_feature("knowledge_rag", supported=supported, permitted=permitted, reason_if_disabled=reason)

    supported, permitted, reason = auth_gate(False)
    set_feature("citations", supported=supported, permitted=permitted, reason_if_disabled=reason)

    # workspace-related features that use backend endpoints (projects/context/artifacts/runs)
    supported, permitted, reason = auth_gate(True)
    set_feature("chat_projects", supported=supported, permitted=permitted, reason_if_disabled=reason)

    supported, permitted, reason = auth_gate(True)
    set_feature("chat_context_manager", supported=supported, permitted=permitted, reason_if_disabled=reason)

    supported, permitted, reason = auth_gate(True)
    set_feature("chat_branches", supported=supported, permitted=permitted, reason_if_disabled=reason)

    supported, permitted, reason = auth_gate(True)
    set_feature("chat_canvas", supported=supported, permitted=permitted, reason_if_disabled=reason)

    supported, permitted, reason = auth_gate(True)
    set_feature("chat_artifacts", supported=supported, permitted=permitted, reason_if_disabled=reason)

    supported, permitted, reason = auth_gate(True)
    set_feature("chat_run_inspector", supported=supported, permitted=permitted, reason_if_disabled=reason)

    # Workflow engine (Phase 4)
    supported, permitted, reason = auth_gate(True)
    set_feature("workflows", supported=supported, permitted=permitted, reason_if_disabled=reason)

    return {
        "meta_version": 1,
        "server": {
            "version": request.app.version,
            "server_time": datetime.now(UTC).isoformat(),
            "uptime_seconds": _uptime_seconds(request),
            "debug": bool(settings.debug),
        },
        "auth": {
            "required": bool(auth_required),
            "authenticated": bool(authenticated),
            "user": user_payload,
            "session_cookie_name": settings.session_cookie_name,
            "csrf": {
                "cookie_name": settings.csrf_cookie_name,
                "header_name": settings.csrf_header_name,
            },
        },
        "capabilities": capabilities,
        "features": features,
    }

