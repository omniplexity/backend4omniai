"""
Admin API endpoints.

Handles admin-only operations like invite management and user administration.
"""

import json
from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import RequireAdmin, delete_user_sessions
from app.core import NotFoundError, ValidationError
from app.core.metrics import metrics
from app.db import get_db
from app.db.models import User
from app.db.repositories import (
    AuditAction,
    create_invite,
    get_all_invites,
    get_user_by_id,
    get_user_quota,
    list_audit_entries,
    list_usage_entries,
    list_users_with_quota,
    log_audit,
    log_invite_create,
    log_user_disable,
    update_user_quota,
    update_user_status,
)

router = APIRouter(prefix="/admin", tags=["admin"])


# Request/Response schemas
class CreateInviteRequest(BaseModel):
    """Create invite request body."""

    expires_in_seconds: int = Field(
        default=604800,  # 7 days
        ge=60,  # Minimum 1 minute
        le=2592000,  # Maximum 30 days
        description="Time until invite expires (seconds)",
    )
    max_uses: int = Field(
        default=1,
        ge=1,
        le=100,
        description="Maximum number of times invite can be used",
    )


class InviteResponse(BaseModel):
    """Invite response."""

    id: str
    code: str
    created_by: str | None
    expires_at: str
    max_uses: int
    use_count: int
    used_by: str | None
    used_at: str | None
    created_at: str


class UserStatusRequest(BaseModel):
    """User status update request."""

    status: str = Field(..., pattern=r"^(active|disabled)$")


class UpdateAdminUserRequest(BaseModel):
    """Patch payload for admin user updates."""

    status: str | None = Field(None, pattern=r"^(active|disabled)$")
    messages_per_day: int | None = Field(None, ge=0)
    tokens_per_day: int | None = Field(None, ge=0)

    class Config:
        extra = "forbid"


class AdminUserResponse(BaseModel):
    """Response model for admin user listing."""

    id: str
    username: str
    email: str | None
    role: str
    status: str
    quotas: dict[str, Any] | None


class UsageEntryResponse(BaseModel):
    """Response model for usage counter entries."""

    user_id: str
    username: str | None
    date: str
    messages_used: int
    tokens_used: int


class AuditEntryResponse(BaseModel):
    """Response model for audit log entries."""

    id: str
    actor_user_id: str | None
    action: str
    target_type: str | None
    target_id: str | None
    details: dict[str, Any] | None
    created_at: str


def get_client_ip(request: Request) -> str | None:
    """Extract client IP address from request."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _admin_user_response(user) -> dict[str, Any]:
    quota = getattr(user, "quota", None)
    quotas = None
    if quota:
        quotas = {
            "messages_per_day": quota.messages_per_day,
            "tokens_per_day": quota.tokens_per_day,
            "reset_at": quota.reset_at.isoformat() if quota.reset_at else None,
        }
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        status=user.status,
        quotas=quotas,
    ).model_dump()


def _usage_entry_response(entry, username_map: dict[str, str | None]) -> dict[str, Any]:
    return UsageEntryResponse(
        user_id=entry.user_id,
        username=username_map.get(entry.user_id),
        date=entry.date.isoformat(),
        messages_used=entry.messages_used,
        tokens_used=entry.tokens_used,
    ).model_dump()


def _audit_entry_response(entry) -> dict[str, Any]:
    details = None
    if entry.details:
        try:
            details = json.loads(entry.details)
        except json.JSONDecodeError:
            details = None
    return AuditEntryResponse(
        id=entry.id,
        actor_user_id=entry.actor_user_id,
        action=entry.action,
        target_type=entry.target_type,
        target_id=entry.target_id,
        details=details,
        created_at=entry.created_at.isoformat(),
    ).model_dump()


@router.post("/invites")
async def create_invite_code(
    request: Request,
    body: CreateInviteRequest,
    auth: RequireAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """
    Create a new invite code.

    Requires admin role.
    """
    admin_user, _ = auth
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("user-agent")

    # Create invite
    invite = create_invite(
        db,
        created_by=admin_user.id,
        expires_in_seconds=body.expires_in_seconds,
        max_uses=body.max_uses,
    )

    # Log event
    log_invite_create(
        db,
        admin_user_id=admin_user.id,
        invite_id=invite.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return {
        "invite": InviteResponse(
            id=invite.id,
            code=invite.code,
            created_by=invite.created_by,
            expires_at=invite.expires_at.isoformat(),
            max_uses=invite.max_uses,
            use_count=invite.use_count,
            used_by=invite.used_by,
            used_at=invite.used_at.isoformat() if invite.used_at else None,
            created_at=invite.created_at.isoformat(),
        ).model_dump()
    }


@router.get("/invites")
async def list_invites(
    _auth: RequireAdmin,  # noqa: ARG001 - Required for admin auth
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """
    List all invite codes.

    Requires admin role.
    """
    invites = get_all_invites(db)

    return {
        "invites": [
            InviteResponse(
                id=inv.id,
                code=inv.code,
                created_by=inv.created_by,
                expires_at=inv.expires_at.isoformat(),
                max_uses=inv.max_uses,
                use_count=inv.use_count,
                used_by=inv.used_by,
                used_at=inv.used_at.isoformat() if inv.used_at else None,
                created_at=inv.created_at.isoformat(),
            ).model_dump()
            for inv in invites
        ]
    }


@router.get("/users")
async def list_users_route(
    _auth: RequireAdmin,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List users with quota metadata."""
    users = list_users_with_quota(db, limit=limit, offset=offset)
    return {
        "users": [_admin_user_response(user) for user in users],
        "limit": limit,
        "offset": offset,
    }


@router.patch("/users/{user_id}")
async def update_user_route(
    request: Request,
    user_id: str,
    body: UpdateAdminUserRequest,
    auth: RequireAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """
    Update a user's status or quotas.
    """
    admin_user, _ = auth
    target_user = get_user_by_id(db, user_id)
    if not target_user:
        raise NotFoundError(f"User {user_id} not found")

    fields = body.__fields_set__
    if "status" in fields and body.status:
        if body.status == "disabled" and target_user.id == admin_user.id:
            raise ValidationError("Cannot disable your own account")
        updated = update_user_status(db, user_id, body.status)
        if updated and body.status == "disabled":
            delete_user_sessions(db, user_id)
            log_user_disable(
                db,
                admin_user_id=admin_user.id,
                target_user_id=user_id,
                ip_address=get_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
        elif updated and body.status == "active":
            log_audit(
                db,
                action=AuditAction.USER_ENABLE,
                actor_user_id=admin_user.id,
                target_type="user",
                target_id=user_id,
                ip_address=get_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
        target_user = updated or target_user

    quota_changed = bool(
        {"messages_per_day", "tokens_per_day"} & fields
    )
    if quota_changed:
        existing = get_user_quota(db, user_id)
        messages = existing.messages_per_day if existing else None
        tokens = existing.tokens_per_day if existing else None
        if "messages_per_day" in fields:
            messages = body.messages_per_day
        if "tokens_per_day" in fields:
            tokens = body.tokens_per_day
        update_user_quota(
            db,
            user_id,
            messages_per_day=messages,
            tokens_per_day=tokens,
        )
        log_audit(
            db,
            action=AuditAction.USER_QUOTA_UPDATE,
            actor_user_id=admin_user.id,
            target_type="user",
            target_id=user_id,
            details={"messages_per_day": messages, "tokens_per_day": tokens},
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )

    return {"user": _admin_user_response(target_user)}


@router.get("/usage")
async def list_usage_route(
    _auth: RequireAdmin,
    db: Annotated[Session, Depends(get_db)],
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """
    Return usage summaries over the requested date range.
    """
    today = datetime.utcnow().date()
    start = date.fromisoformat(from_date) if from_date else today - timedelta(days=6)
    end = date.fromisoformat(to_date) if to_date else today
    if start > end:
        raise ValidationError("Invalid usage window")
    entries = list_usage_entries(db, start_date=start, end_date=end, limit=limit, offset=offset)
    user_ids = {entry.user_id for entry in entries}
    username_map: dict[str, str | None] = {}
    if user_ids:
        stmt = select(User.id, User.username).where(User.id.in_(user_ids))
        for user_id_val, username in db.execute(stmt).all():
            username_map[user_id_val] = username
    return {
        "entries": [_usage_entry_response(entry, username_map) for entry in entries],
        "limit": limit,
        "offset": offset,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }


@router.get("/audit")
async def list_audit_route(
    _auth: RequireAdmin,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """
    List recent audit entries.
    """
    entries = list_audit_entries(db, limit=limit, offset=offset)
    return {
        "entries": [_audit_entry_response(entry) for entry in entries],
        "limit": limit,
        "offset": offset,
    }


@router.get("/metrics")
async def admin_metrics_route(
    _auth: RequireAdmin,
) -> dict[str, Any]:
    """Return lightweight metrics for troubleshooting."""
    return {"metrics": metrics.snapshot()}


@router.post("/users/{user_id}/disable")
async def disable_user(
    request: Request,
    user_id: str,
    auth: RequireAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """
    Disable a user account.

    Requires admin role. Cannot disable yourself.
    """
    admin_user, _ = auth
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("user-agent")

    # Check target user exists
    target_user = get_user_by_id(db, user_id)
    if not target_user:
        raise NotFoundError(f"User {user_id} not found")

    # Prevent self-disable
    if target_user.id == admin_user.id:
        from app.core import ValidationError

        raise ValidationError("Cannot disable your own account")

    # Update status
    updated_user = update_user_status(db, user_id, "disabled")

    # Delete all sessions for disabled user
    delete_user_sessions(db, user_id)

    # Log event
    log_user_disable(
        db,
        admin_user_id=admin_user.id,
        target_user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return {
        "user": {
            "id": updated_user.id,
            "username": updated_user.username,
            "status": updated_user.status,
        }
    }


@router.post("/users/{user_id}/enable")
async def enable_user(
    request: Request,
    user_id: str,
    auth: RequireAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """
    Enable a previously disabled user account.

    Requires admin role.
    """
    admin_user, _ = auth
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("user-agent")

    # Check target user exists
    target_user = get_user_by_id(db, user_id)
    if not target_user:
        raise NotFoundError(f"User {user_id} not found")

    # Update status
    updated_user = update_user_status(db, user_id, "active")

    # Log event (using user_disable with "enable" in details would be cleaner,
    # but we're keeping it simple)
    log_audit(
        db,
        action=AuditAction.USER_ENABLE,
        actor_user_id=admin_user.id,
        target_type="user",
        target_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return {
        "user": {
            "id": updated_user.id,
            "username": updated_user.username,
            "status": updated_user.status,
        }
    }
