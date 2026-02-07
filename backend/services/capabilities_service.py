"""Service capability helpers.

Used by both `/capabilities` (health API) and `/v1/meta` to avoid drift.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.services.tool_capabilities_service import get_tool_capabilities


async def compute_service_capabilities(registry: Any | None) -> Dict[str, Any]:
    """Compute backend capabilities for frontend feature gating."""

    voice_providers: list[dict[str, Any]] = []
    streaming_providers: list[str] = []

    if registry is not None:
        for provider_id, provider in getattr(registry, "providers", {}).items():
            try:
                caps = await provider.capabilities()
            except Exception:
                continue

            # Voice
            if getattr(caps, "voice", False) or getattr(caps, "stt", False) or getattr(caps, "tts", False) or getattr(caps, "voices", False):
                voice_providers.append(
                    {
                        "id": provider_id,
                        "name": provider_id,
                        "stt": bool(getattr(caps, "stt", False)),
                        "tts": bool(getattr(caps, "tts", False)),
                        "voices": bool(getattr(caps, "voices", False)),
                    }
                )

            # Streaming
            if bool(getattr(caps, "streaming", False)):
                streaming_providers.append(provider_id)

    tools_caps = get_tool_capabilities()

    return {
        "streaming": {
            "sse": True,  # Backend supports SSE endpoints
            "polling": True,  # Backend supports polling fallback (legacy)
            "retry": True,
            "providers": streaming_providers,
        },
        "voice": {
            "available": len(voice_providers) > 0,
            "stt": any(p.get("stt") for p in voice_providers),
            "tts": any(p.get("tts") for p in voice_providers),
            "voices": any(p.get("voices") for p in voice_providers),
            "providers": voice_providers,
        },
        "vision": {
            "image_input": False,
            "screenshot_analyze": False,
        },
        "tools": {
            "mcp": bool(tools_caps.get("supports_mcp")),
            "connectors": bool(tools_caps.get("supports_connectors")),
        },
        "media": {
            "img2img": False,
            "img2video": False,
        },
        "attachments": {
            "images": True,
            "max_size_mb": 5,
            "max_count": 6,
        },
    }

