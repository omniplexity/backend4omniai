from __future__ import annotations

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.orm import Session


def write_audit(
    db: Session,
    actor_user_id: int | None,
    action: str,
    target: str,
    request: Request,
) -> None:
    """Write an audit log entry."""
    from backend.app.config.settings import settings

    # Get IP: prefer real client IP from headers if behind trusted tunnel
    ip = request.client.host if request.client else None
    proxy_ip = None
    if settings.origin_lock_enabled and request.headers.get("X-Origin-Secret") == settings.origin_lock_secret:
        # Trust forwarded headers only when origin lock passes
        cf_ip = request.headers.get("CF-Connecting-IP")  # Cloudflare
        if cf_ip:
            proxy_ip = cf_ip
            ip = cf_ip
        else:
            x_forwarded_for = request.headers.get("X-Forwarded-For")
            if x_forwarded_for:
                # Take first IP if multiple
                proxy_ip = x_forwarded_for.split(",")[0].strip()
                ip = proxy_ip

    user_agent = request.headers.get("User-Agent")

    from datetime import datetime, timezone
    db.execute(
        text("""
            INSERT INTO audit_log (action, target, actor_user_id, ip, proxy_ip, user_agent, created_at)
            VALUES (:action, :target, :actor_user_id, :ip, :proxy_ip, :user_agent, :created_at)
        """),
        {
            "action": action,
            "target": target,
            "actor_user_id": actor_user_id,
            "ip": ip,
            "proxy_ip": proxy_ip,
            "user_agent": user_agent,
            "created_at": datetime.now(timezone.utc),
        }
    )
    # No flush needed; will be committed with the transaction