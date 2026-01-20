from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.auth.audit import write_audit
from backend.app.auth.csrf import require_csrf
from backend.app.auth.deps import require_admin
from backend.app.auth.password import hash_password
from backend.app.auth.sessions import create_session
from backend.app.config.settings import settings
from backend.app.db.models import AuditLog, Invite, User, UserQuota
from backend.app.db.repo.invites_repo import create_invite
from backend.app.db.repo.users_repo import create_user, get_user_by_username
from backend.app.db.session import get_db
from backend.app.services.quota_service import get_or_create_quota

router = APIRouter(prefix="/admin", tags=["admin"])


class BootstrapRequest(BaseModel):
    username: str
    password: str


class CreateInviteRequest(BaseModel):
    expires_in_hours: int = 24


class UpdateUserRequest(BaseModel):
    status: str | None = None  # "active" or "disabled"
    role: str | None = None  # "user" or "admin"


class UpdateQuotaRequest(BaseModel):
    messages_per_day: int
    tokens_per_day: int


@router.post("/bootstrap")
def bootstrap_admin(request: Request, body: BootstrapRequest, db: Session = Depends(get_db)) -> JSONResponse:
    admin_exists = db.query(User).filter(User.role == "admin").first() is not None
    if admin_exists:
        raise HTTPException(status_code=403, detail={"code": "BOOTSTRAP_DISABLED", "message": "Admin already exists"})

    token = request.headers.get("X-Bootstrap-Token") or request.query_params.get("token")
    if settings.admin_bootstrap_token and token != settings.admin_bootstrap_token:
        raise HTTPException(status_code=403, detail={"code": "INVALID_BOOTSTRAP_TOKEN", "message": "Invalid bootstrap token"})

    if get_user_by_username(db, body.username):
        raise HTTPException(status_code=409, detail={"code": "USERNAME_EXISTS", "message": "Username already exists"})

    admin = create_user(db, username=body.username, password_hash=hash_password(body.password), role="admin", status="active")
    session_id, csrf_token = create_session(db, admin.id, device_meta=request.headers.get("User-Agent"))
    write_audit(db, admin.id, "ADMIN_BOOTSTRAP", f"user:{admin.id}", request)
    db.commit()

    resp = JSONResponse(content={"user": {"id": admin.id, "username": admin.username, "role": admin.role, "status": admin.status},
                                "csrf_token": csrf_token})
    resp.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=str(settings.cookie_samesite).lower(),
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    return resp


@router.post("/invites", dependencies=[Depends(require_csrf)])
def create_invite_endpoint(
    request: Request,
    body: CreateInviteRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Create a new invite code (admin only)."""

    import secrets
    code = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=body.expires_in_hours)

    invite = create_invite(db, code=code, expires_at=expires_at, created_by=admin.id)

    write_audit(db, admin.id, "INVITE_CREATED", f"invite:{invite.code}", request)
    db.commit()

    return {
        "invite_code": invite.code,
        "expires_at": invite.expires_at.isoformat(),
    }


@router.get("/invites")
def list_invites(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """List recent invites (admin only)."""
    invites = db.query(Invite).order_by(Invite.created_at.desc()).limit(50).all()
    return {
        "invites": [
            {
                "code": invite.code,
                "created_by": invite.created_by,
                "used_by": invite.used_by,
                "expires_at": invite.expires_at.isoformat(),
                "revoked_at": invite.revoked_at.isoformat() if invite.revoked_at else None,
                "created_at": invite.created_at.isoformat(),
            }
            for invite in invites
        ]
    }


@router.get("/users")
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """List all users (admin only)."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return {
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role,
                "status": user.status,
                "created_at": user.created_at.isoformat(),
                "last_login": user.last_login.isoformat() if user.last_login else None,
            }
            for user in users
        ]
    }


@router.patch("/users/{user_id}", dependencies=[Depends(require_csrf)])
def update_user(
    user_id: int,
    request: Request,
    body: UpdateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Update user status/role (admin only)."""

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND", "message": "User not found"})

    # Validate inputs
    if body.status and body.status not in ["active", "disabled"]:
        raise HTTPException(status_code=400, detail={"code": "INVALID_STATUS", "message": "Status must be 'active' or 'disabled'"})
    if body.role and body.role not in ["user", "admin"]:
        raise HTTPException(status_code=400, detail={"code": "INVALID_ROLE", "message": "Role must be 'user' or 'admin'"})

    # Update fields
    if body.status:
        user.status = body.status
    if body.role:
        user.role = body.role

    write_audit(db, admin.id, "USER_UPDATED", f"user:{user.id}", request)
    db.commit()

    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "status": user.status,
    }


@router.get("/quotas/{user_id}")
def get_user_quota(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Get user quota (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND", "message": "User not found"})

    quota = get_or_create_quota(db, user_id)
    return {
        "user_id": user_id,
        "messages_per_day": quota.messages_per_day,
        "tokens_per_day": quota.tokens_per_day,
        "updated_at": quota.updated_at.isoformat(),
    }


@router.put("/quotas/{user_id}", dependencies=[Depends(require_csrf)])
def update_user_quota(
    user_id: int,
    request: Request,
    body: UpdateQuotaRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Update user quota (admin only)."""

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND", "message": "User not found"})

    quota = get_or_create_quota(db, user_id)
    quota.messages_per_day = body.messages_per_day
    quota.tokens_per_day = body.tokens_per_day

    write_audit(db, admin.id, "QUOTA_UPDATED", f"user:{user_id}", request)
    db.commit()

    return {
        "user_id": user_id,
        "messages_per_day": quota.messages_per_day,
        "tokens_per_day": quota.tokens_per_day,
        "updated_at": quota.updated_at.isoformat(),
    }


@router.post("/invites/{code}/revoke", dependencies=[Depends(require_csrf)])
def revoke_invite(
    code: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Revoke an invite (admin only)."""

    invite = db.query(Invite).filter(Invite.code == code).first()
    if not invite:
        raise HTTPException(status_code=404, detail={"code": "INVITE_NOT_FOUND", "message": "Invite not found"})

    if invite.revoked_at:
        raise HTTPException(status_code=400, detail={"code": "ALREADY_REVOKED", "message": "Invite already revoked"})

    invite.revoked_at = datetime.now(timezone.utc)

    write_audit(db, admin.id, "INVITE_REVOKED", f"invite:{code}", request)
    db.commit()

    return {
        "code": code,
        "revoked_at": invite.revoked_at.isoformat(),
    }


@router.get("/audit")
def get_audit_log(
    q: str | None = None,
    action: str | None = None,
    actor_user_id: int | None = None,
    since: str | None = None,  # ISO datetime
    limit: int = 200,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Get audit log entries (admin only)."""
    if limit > 200:
        limit = 200

    query = db.query(AuditLog)

    if q:
        query = query.filter(AuditLog.target.contains(q))
    if action:
        query = query.filter(AuditLog.action == action)
    if actor_user_id:
        query = query.filter(AuditLog.actor_user_id == actor_user_id)
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
            query = query.filter(AuditLog.created_at >= since_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail={"code": "INVALID_SINCE", "message": "Invalid since datetime"})

    entries = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

    return {
        "entries": [
            {
                "id": entry.id,
                "action": entry.action,
                "target": entry.target,
                "actor_user_id": entry.actor_user_id,
                "ip": entry.ip,
                "user_agent": entry.user_agent,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in entries
        ]
    }