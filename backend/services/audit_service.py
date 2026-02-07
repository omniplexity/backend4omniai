"""Audit logging service.

Phase 1 requirement: persistent audit logs.

This is intentionally small: it provides a single helper to record an event.
We can expand this into a richer policy later (PII redaction, event taxonomy,
admin views, export).
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session as DBSession

from backend.db.models import AuditLog


def _client_ip_from_request(request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None
    if request.client:
        return request.client.host
    return None


def audit_log_event(
    db: DBSession,
    *,
    event_type: str,
    user_id: Optional[str],
    request=None,
    data: Optional[dict[str, Any]] = None,
) -> None:
    """Persist an audit log entry.

    This should never fail the request path; failures should be treated as best-effort.
    """
    try:
        ip = _client_ip_from_request(request) if request is not None else None
        user_agent = request.headers.get("user-agent") if request is not None else None
        path = request.url.path if request is not None else None
        method = request.method if request is not None else None

        entry = AuditLog(
            user_id=user_id,
            event_type=event_type,
            ip=ip,
            user_agent=user_agent,
            path=path,
            method=method,
            data_json=data,
        )
        db.add(entry)
        db.commit()
    except Exception:
        # Best-effort only: do not raise.
        db.rollback()

