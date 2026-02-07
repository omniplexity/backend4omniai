"""Time helpers.

We keep DB timestamps naive (no tzinfo) but always in UTC to avoid mixing
offset-aware/naive datetimes while remaining explicit about the timezone.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC datetime (tzinfo stripped)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

