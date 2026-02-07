"""Tool capability helpers.

This module centralizes tool capability reporting so API endpoints and
meta/capabilities contracts cannot drift.
"""

from __future__ import annotations

from typing import Any, Dict


def get_tool_capabilities() -> Dict[str, Any]:
    """Return the backend's tool subsystem capabilities.

    Notes:
    - These values reflect whether endpoints exist and are intended to be used.
    - Configuration/availability of specific servers/connectors is exposed via meta.details.
    """

    return {
        "supports_receipts": True,
        "supports_favorites": True,
        "supports_mcp": True,
        "supports_connectors": True,
    }

