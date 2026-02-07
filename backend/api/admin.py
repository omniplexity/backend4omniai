"""Admin API endpoints."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_admin_user, get_current_user
from backend.auth.session import get_user_sessions, revoke_all_user_sessions, revoke_session_by_id
from backend.core.logging import get_logger
from backend.core.time import utcnow
from backend.db import get_db
from backend.db.models import AuditLog, InviteCode, Session, User
from backend.services.audit_service import audit_log_event

logger = get_logger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])

# In-memory provider configuration (would be moved to database in production)
_provider_configs: dict = {}


class UserListResponse(BaseModel):
    """User list item."""

    id: str
    email: str
    username: str
    is_active: bool
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class InviteCodeResponse(BaseModel):
    """Invite code response."""

    id: str
    code: str
    created_by: Optional[str]
    used_by: Optional[str]
    expires_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogResponse(BaseModel):
    id: str
    user_id: Optional[str]
    event_type: str
    ip: Optional[str]
    user_agent: Optional[str]
    path: Optional[str]
    method: Optional[str]
    data_json: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


class CreateInviteRequest(BaseModel):
    """Create invite code request."""

    expires_in_days: Optional[int] = Field(default=7, ge=1, le=365)


class UpdateUserRequest(BaseModel):
    """Update user request."""

    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


@router.get("/users", response_model=List[UserListResponse])
async def list_users(
    limit: int = 100,
    offset: int = 0,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """List all users (admin only)."""
    users = db.query(User).order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    return [UserListResponse.model_validate(u) for u in users]


@router.get("/users/{user_id}", response_model=UserListResponse)
async def get_user(
    user_id: str,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Get a specific user (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return UserListResponse.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserListResponse)
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    http_request: Request,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Update a user (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Don't allow admin to demote themselves
    if user.id == admin.id and request.is_admin is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove your own admin status",
        )

    if request.is_active is not None:
        user.is_active = request.is_active
    if request.is_admin is not None:
        user.is_admin = request.is_admin

    db.commit()
    db.refresh(user)

    logger.info(f"Admin {admin.username} updated user {user.username}")
    audit_log_event(
        db,
        event_type="admin.user_update",
        user_id=admin.id,
        request=http_request,
        data={"target_user_id": user.id, "is_active": request.is_active, "is_admin": request.is_admin},
    )

    return UserListResponse.model_validate(user)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    http_request: Request,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Delete a user (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    db.delete(user)
    db.commit()

    logger.info(f"Admin {admin.username} deleted user {user.username}")
    audit_log_event(
        db,
        event_type="admin.user_delete",
        user_id=admin.id,
        request=http_request,
        data={"target_user_id": user.id, "target_username": user.username},
    )

    return {"message": "User deleted"}


@router.get("/invites", response_model=List[InviteCodeResponse])
async def list_invites(
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """List all invite codes (admin only)."""
    invites = db.query(InviteCode).order_by(InviteCode.created_at.desc()).all()
    return [InviteCodeResponse.model_validate(i) for i in invites]


@router.post("/invites", response_model=InviteCodeResponse)
async def create_invite(
    request: CreateInviteRequest,
    http_request: Request,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Create a new invite code (admin only)."""
    code = secrets.token_urlsafe(16)

    expires_at = None
    if request.expires_in_days:
        expires_at = utcnow() + timedelta(days=request.expires_in_days)

    invite = InviteCode(
        code=code,
        created_by=admin.id,
        expires_at=expires_at,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    logger.info(f"Admin {admin.username} created invite code")
    audit_log_event(
        db,
        event_type="admin.invite_create",
        user_id=admin.id,
        request=http_request,
        data={"invite_id": invite.id, "expires_at": invite.expires_at.isoformat() if invite.expires_at else None},
    )

    return InviteCodeResponse.model_validate(invite)


@router.delete("/invites/{invite_id}")
async def delete_invite(
    invite_id: str,
    http_request: Request,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Delete an invite code (admin only)."""
    invite = db.query(InviteCode).filter(InviteCode.id == invite_id).first()
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite code not found",
        )

    db.delete(invite)
    db.commit()

    audit_log_event(
        db,
        event_type="admin.invite_delete",
        user_id=admin.id,
        request=http_request,
        data={"invite_id": invite_id},
    )

    return {"message": "Invite code deleted"}


@router.get("/stats")
async def get_stats(
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Get system statistics (admin only)."""
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    admin_users = db.query(User).filter(User.is_admin == True).count()
    unused_invites = db.query(InviteCode).filter(InviteCode.used_by.is_(None)).count()

    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "admins": admin_users,
        },
        "invites": {
            "unused": unused_invites,
        },
    }


@router.get("/usage")
async def get_usage(
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Return usage metrics (placeholder)."""
    return {"entries": []}


@router.get("/audit")
async def get_audit(
    event: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Return audit entries (admin only)."""
    q = db.query(AuditLog).order_by(AuditLog.created_at.desc())

    if event:
        q = q.filter(AuditLog.event_type == event)

    def _parse_dt(s: str) -> datetime:
        try:
            # Accept date-only (YYYY-MM-DD) or full isoformat.
            if len(s) == 10 and s[4] == "-" and s[7] == "-":
                return datetime.fromisoformat(s).replace(tzinfo=UTC)
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid datetime: {s}") from exc

    if from_date:
        start = _parse_dt(from_date)
        q = q.filter(AuditLog.created_at >= start.replace(tzinfo=None))
    if to_date:
        end = _parse_dt(to_date)
        q = q.filter(AuditLog.created_at <= end.replace(tzinfo=None))

    entries = q.offset(offset).limit(min(500, max(1, limit))).all()
    return {"entries": [AuditLogResponse.model_validate(e) for e in entries]}


# =============================================================================
# Session Management Endpoints
# =============================================================================

class SessionResponse(BaseModel):
    """Session response model."""
    id: str
    created_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class UserSessionsResponse(BaseModel):
    """User sessions response."""
    user_id: str
    sessions: List[SessionResponse]
    count: int


@router.get("/users/{user_id}/sessions", response_model=UserSessionsResponse)
async def get_user_sessions_endpoint(
    user_id: str,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Get all active sessions for a user (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    sessions = get_user_sessions(db, user_id)
    return UserSessionsResponse(
        user_id=user_id,
        sessions=[SessionResponse.model_validate(s) for s in sessions],
        count=len(sessions),
    )


@router.post("/users/{user_id}/sessions/revoke-all")
async def revoke_all_user_sessions_endpoint(
    user_id: str,
    http_request: Request,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Revoke all sessions for a user (admin only).
    
    This logs the user out from all devices.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use logout to revoke your own sessions",
        )

    count = revoke_all_user_sessions(db, user_id)

    logger.info(f"Admin {admin.username} revoked {count} sessions for user {user.username}")
    audit_log_event(
        db,
        event_type="admin.sessions_revoke_all",
        user_id=admin.id,
        request=http_request,
        data={"target_user_id": user.id, "sessions_revoked": count},
    )

    return {
        "message": f"Revoked {count} session(s)",
        "sessions_revoked": count,
    }


@router.delete("/sessions/{session_id}")
async def revoke_session_endpoint(
    session_id: str,
    http_request: Request,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Revoke a specific session (admin only)."""
    # Get session to find user before deleting
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Prevent revoking own session through this endpoint
    if session.user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use logout to revoke your own session",
        )

    success = revoke_session_by_id(db, session_id)

    if success:
        logger.info(f"Admin {admin.username} revoked session {session_id[:8]}...")
        audit_log_event(
            db,
            event_type="admin.session_revoke",
            user_id=admin.id,
            request=http_request,
            data={"target_session_id": session_id, "target_user_id": session.user_id},
        )
        return {"message": "Session revoked"}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )


# =============================================================================
# Provider Management Endpoints
# =============================================================================

class ProviderAdminConfig(BaseModel):
    """Provider configuration for admin."""
    enabled: bool = True
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    timeout: Optional[int] = 30
    priority: Optional[int] = 0
    notes: Optional[str] = None


class ProviderAdminStatus(BaseModel):
    """Provider status for admin."""
    name: str
    enabled: bool
    healthy: bool
    latency_ms: Optional[float] = None
    models_available: Optional[int] = None
    capabilities: dict = {}
    endpoint: Optional[str] = None
    priority: int = 0
    last_checked: Optional[datetime] = None


class UpdateProviderRequest(BaseModel):
    """Update provider request."""
    enabled: Optional[bool] = None
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    timeout: Optional[int] = None
    priority: Optional[int] = None
    notes: Optional[str] = None


@router.get("/providers")
async def list_providers_admin(
    request: Request,
    admin: User = Depends(get_admin_user),
):
    """List all providers with admin-level details."""
    registry = getattr(request.app.state, "provider_registry", None)
    
    if not registry:
        return {"providers": [], "default": None}
    
    providers = []
    for name in registry.list_providers():
        provider = registry.get_provider(name)
        if not provider:
            continue
            
        # Get health status
        healthy = False
        latency_ms = None
        models_available = None
        capabilities = {}
        endpoint = None
        
        try:
            import time
            start = time.perf_counter()
            healthy = await provider.healthcheck()
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
        except Exception:
            pass
        
        # Get capabilities
        try:
            caps = await provider.capabilities()
            capabilities = {
                "streaming": caps.streaming,
                "function_calling": caps.function_calling,
                "vision": caps.vision,
                "embeddings": caps.embeddings,
                "voice": caps.voice,
                "stt": caps.stt,
                "tts": caps.tts,
            }
        except Exception:
            pass
        
        # Get model count
        try:
            models = await provider.list_models()
            models_available = len(models)
        except Exception:
            pass
        
        # Get endpoint
        if hasattr(provider, "base_url"):
            endpoint = provider.base_url
        
        # Get stored config
        config = _provider_configs.get(name, {})
        
        providers.append({
            "name": name,
            "enabled": config.get("enabled", True),
            "healthy": healthy,
            "latency_ms": latency_ms,
            "models_available": models_available,
            "capabilities": capabilities,
            "endpoint": endpoint,
            "priority": config.get("priority", 0),
            "notes": config.get("notes"),
            "is_default": name == registry.default_provider,
        })
    
    return {
        "providers": providers,
        "default": registry.default_provider,
    }


@router.get("/providers/{provider_name}")
async def get_provider_admin(
    provider_name: str,
    request: Request,
    admin: User = Depends(get_admin_user),
):
    """Get detailed provider information."""
    registry = getattr(request.app.state, "provider_registry", None)
    
    if not registry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No providers configured",
        )
    
    provider = registry.get_provider(provider_name)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider not found: {provider_name}",
        )
    
    # Get full diagnostics
    config = _provider_configs.get(provider_name, {})
    
    return {
        "name": provider_name,
        "config": config,
        "is_default": provider_name == registry.default_provider,
    }


@router.patch("/providers/{provider_name}")
async def update_provider_admin(
    provider_name: str,
    request_data: UpdateProviderRequest,
    http_request: Request,
    admin: User = Depends(get_admin_user),
):
    """Update provider configuration."""
    registry = getattr(request.app.state, "provider_registry", None)
    
    if not registry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No providers configured",
        )
    
    provider = registry.get_provider(provider_name)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider not found: {provider_name}",
        )
    
    # Update stored config
    if provider_name not in _provider_configs:
        _provider_configs[provider_name] = {}
    
    update_data = request_data.model_dump(exclude_unset=True)
    _provider_configs[provider_name].update(update_data)
    
    logger.info(f"Admin {admin.username} updated provider {provider_name}")
    audit_log_event(
        None,  # No DB needed for in-memory config
        event_type="admin.provider_update",
        user_id=admin.id,
        request=http_request,
        data={"provider": provider_name, "updates": list(update_data.keys())},
    )
    
    return {
        "message": "Provider updated",
        "provider": provider_name,
        "config": _provider_configs[provider_name],
    }


@router.post("/providers/{provider_name}/check")
async def check_provider_health(
    provider_name: str,
    request: Request,
    admin: User = Depends(get_admin_user),
):
    """Trigger a health check for a provider."""
    registry = getattr(request.app.state, "provider_registry", None)
    
    if not registry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No providers configured",
        )
    
    provider = registry.get_provider(provider_name)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider not found: {provider_name}",
        )
    
    import time
    start = time.perf_counter()
    
    try:
        healthy = await provider.healthcheck()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        
        return {
            "provider": provider_name,
            "healthy": healthy,
            "latency_ms": latency_ms,
            "timestamp": utcnow().isoformat(),
        }
    except Exception as e:
        return {
            "provider": provider_name,
            "healthy": False,
            "error": str(e),
            "timestamp": utcnow().isoformat(),
        }


@router.post("/providers/{provider_name}/set-default")
async def set_default_provider(
    provider_name: str,
    http_request: Request,
    admin: User = Depends(get_admin_user),
):
    """Set the default provider."""
    registry = getattr(request.app.state, "provider_registry", None)
    
    if not registry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No providers configured",
        )
    
    provider = registry.get_provider(provider_name)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider not found: {provider_name}",
        )
    
    registry.default_provider = provider_name
    
    logger.info(f"Admin {admin.username} set default provider to {provider_name}")
    audit_log_event(
        None,
        event_type="admin.provider_set_default",
        user_id=admin.id,
        request=http_request,
        data={"provider": provider_name},
    )
    
    return {"message": f"Default provider set to {provider_name}"}


# =============================================================================
# Project & Data Management Endpoints
# =============================================================================

class ProjectAdminResponse(BaseModel):
    """Project response for admin."""
    id: str
    name: str
    user_id: str
    username: Optional[str] = None
    instructions: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    conversation_count: int = 0

    class Config:
        from_attributes = True


class MemoryEntryAdminResponse(BaseModel):
    """Memory entry response for admin."""
    id: str
    user_id: str
    username: Optional[str] = None
    title: str
    content: str
    tags: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KnowledgeDocAdminResponse(BaseModel):
    """Knowledge document response for admin."""
    id: str
    user_id: str
    username: Optional[str] = None
    name: str
    mime_type: Optional[str] = None
    size: Optional[int] = None
    created_at: datetime
    chunk_count: int = 0

    class Config:
        from_attributes = True


@router.get("/projects", response_model=List[ProjectAdminResponse])
async def list_projects_admin(
    user_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """List all projects with optional user filter (admin only)."""
    from backend.db.models import Project, Conversation
    from sqlalchemy import func

    query = db.query(
        Project,
        User.username.label('username'),
        func.count(Conversation.id).label('conversation_count')
    ).join(
        User, Project.user_id == User.id
    ).outerjoin(
        Conversation, Project.id == Conversation.project_id
    ).group_by(Project.id)

    if user_id:
        query = query.filter(Project.user_id == user_id)

    results = query.order_by(Project.created_at.desc()).offset(offset).limit(limit).all()

    projects = []
    for project, username, conversation_count in results:
        proj_dict = {
            "id": project.id,
            "name": project.name,
            "user_id": project.user_id,
            "username": username,
            "instructions": project.instructions,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
            "conversation_count": conversation_count,
        }
        projects.append(ProjectAdminResponse.model_validate(proj_dict))

    return projects


@router.delete("/projects/{project_id}")
async def delete_project_admin(
    project_id: str,
    http_request: Request,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Delete a project and all its data (admin only)."""
    from backend.db.models import Project

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    project_name = project.name
    user_id = project.user_id

    db.delete(project)
    db.commit()

    logger.info(f"Admin {admin.username} deleted project {project_name}")
    audit_log_event(
        db,
        event_type="admin.project_delete",
        user_id=admin.id,
        request=http_request,
        data={"project_id": project_id, "project_name": project_name, "user_id": user_id},
    )

    return {"message": "Project deleted"}


@router.get("/memory", response_model=List[MemoryEntryAdminResponse])
async def list_memory_admin(
    user_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """List all memory entries with optional filters (admin only)."""
    from backend.db.models import MemoryEntry

    query = db.query(
        MemoryEntry,
        User.username.label('username')
    ).join(
        User, MemoryEntry.user_id == User.id
    )

    if user_id:
        query = query.filter(MemoryEntry.user_id == user_id)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (MemoryEntry.title.ilike(search_filter)) |
            (MemoryEntry.content.ilike(search_filter))
        )

    results = query.order_by(MemoryEntry.created_at.desc()).offset(offset).limit(limit).all()

    memory_entries = []
    for entry, username in results:
        entry_dict = {
            "id": entry.id,
            "user_id": entry.user_id,
            "username": username,
            "title": entry.title,
            "content": entry.content[:200] + "..." if len(entry.content) > 200 else entry.content,
            "tags": entry.tags,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }
        memory_entries.append(MemoryEntryAdminResponse.model_validate(entry_dict))

    return memory_entries


@router.delete("/memory/{memory_id}")
async def delete_memory_admin(
    memory_id: str,
    http_request: Request,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Delete a memory entry (admin only)."""
    from backend.db.models import MemoryEntry

    entry = db.query(MemoryEntry).filter(MemoryEntry.id == memory_id).first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory entry not found",
        )

    user_id = entry.user_id
    title = entry.title

    db.delete(entry)
    db.commit()

    logger.info(f"Admin {admin.username} deleted memory entry {title}")
    audit_log_event(
        db,
        event_type="admin.memory_delete",
        user_id=admin.id,
        request=http_request,
        data={"memory_id": memory_id, "title": title, "user_id": user_id},
    )

    return {"message": "Memory entry deleted"}


@router.get("/knowledge", response_model=List[KnowledgeDocAdminResponse])
async def list_knowledge_admin(
    user_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """List all knowledge documents with optional user filter (admin only)."""
    from backend.db.models import KnowledgeDocument, KnowledgeChunk
    from sqlalchemy import func

    query = db.query(
        KnowledgeDocument,
        User.username.label('username'),
        func.count(KnowledgeChunk.id).label('chunk_count')
    ).join(
        User, KnowledgeDocument.user_id == User.id
    ).outerjoin(
        KnowledgeChunk, KnowledgeDocument.id == KnowledgeChunk.doc_id
    ).group_by(KnowledgeDocument.id)

    if user_id:
        query = query.filter(KnowledgeDocument.user_id == user_id)

    results = query.order_by(KnowledgeDocument.created_at.desc()).offset(offset).limit(limit).all()

    docs = []
    for doc, username, chunk_count in results:
        doc_dict = {
            "id": doc.id,
            "user_id": doc.user_id,
            "username": username,
            "name": doc.name,
            "mime_type": doc.mime_type,
            "size": doc.size,
            "created_at": doc.created_at,
            "chunk_count": chunk_count,
        }
        docs.append(KnowledgeDocAdminResponse.model_validate(doc_dict))

    return docs


@router.delete("/knowledge/{doc_id}")
async def delete_knowledge_admin(
    doc_id: str,
    http_request: Request,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Delete a knowledge document and all its chunks (admin only)."""
    from backend.db.models import KnowledgeDocument

    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge document not found",
        )

    user_id = doc.user_id
    name = doc.name

    db.delete(doc)
    db.commit()

    logger.info(f"Admin {admin.username} deleted knowledge doc {name}")
    audit_log_event(
        db,
        event_type="admin.knowledge_delete",
        user_id=admin.id,
        request=http_request,
        data={"doc_id": doc_id, "name": name, "user_id": user_id},
    )

    return {"message": "Knowledge document deleted"}


# =============================================================================
# Export Wizard Endpoints
# =============================================================================

import io
import csv
import json
from typing import Literal

ExportFormat = Literal["json", "csv", "markdown", "pdf"]

class ExportRequest(BaseModel):
    """Export request model."""
    data_types: List[str]  # users, audit, diagnostics, providers, memory, knowledge
    format: ExportFormat = "json"
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    redact_pii: bool = True
    include_metadata: bool = True


class ExportJobResponse(BaseModel):
    """Export job response."""
    job_id: str
    status: str  # pending, processing, completed, failed
    created_at: str
    expires_at: Optional[str] = None
    download_url: Optional[str] = None
    filename: Optional[str] = None
    size_bytes: Optional[int] = None
    error_message: Optional[str] = None


# In-memory export job storage (would use Redis/database in production)
_export_jobs: Dict[str, Dict] = {}


def _generate_export_id() -> str:
    """Generate a unique export job ID."""
    return secrets.token_urlsafe(16)


def _redact_sensitive_data(data: Dict, redact: bool) -> Dict:
    """Redact PII from data."""
    if not redact:
        return data
    
    redacted = {}
    for key, value in data.items():
        if key in ("email", "password", "api_key", "secret", "token"):
            redacted[key] = "***REDACTED***"
        elif isinstance(value, dict):
            redacted[key] = _redact_sensitive_data(value, redact)
        elif isinstance(value, list):
            redacted[key] = [_redact_sensitive_data(item, redact) if isinstance(item, dict) else item for item in value]
        else:
            redacted[key] = value
    return redacted


def _format_as_csv(data: List[Dict]) -> str:
    """Convert data to CSV format."""
    if not data:
        return ""
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()


def _format_as_markdown(data: List[Dict], title: str) -> str:
    """Convert data to Markdown format."""
    if not data:
        return f"# {title}\n\nNo data available."
    
    lines = [f"# {title}", ""]
    
    # Table header
    headers = list(data[0].keys())
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---" for _ in headers]) + " |")
    
    # Table rows
    for row in data:
        values = [str(row.get(h, "")) for h in headers]
        lines.append("| " + " | ".join(values) + " |")
    
    return "\n".join(lines)


async def _collect_export_data(
    db: DBSession,
    data_types: List[str],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    request: Request,
) -> Dict[str, List[Dict]]:
    """Collect data for export based on types."""
    from backend.db.models import Project, MemoryEntry, KnowledgeDocument
    data = {}
    
    for data_type in data_types:
        if data_type == "users":
            users_query = db.query(User)
            if date_from:
                users_query = users_query.filter(User.created_at >= date_from)
            if date_to:
                users_query = users_query.filter(User.created_at <= date_to)
            users = users_query.all()
            data["users"] = [
                {
                    "id": u.id,
                    "username": u.username,
                    "email": u.email,
                    "is_active": u.is_active,
                    "is_admin": u.is_admin,
                    "created_at": u.created_at.isoformat(),
                }
                for u in users
            ]
        
        elif data_type == "audit":
            audit_query = db.query(AuditLog)
            if date_from:
                audit_query = audit_query.filter(AuditLog.created_at >= date_from)
            if date_to:
                audit_query = audit_query.filter(AuditLog.created_at <= date_to)
            logs = audit_query.order_by(AuditLog.created_at.desc()).limit(1000).all()
            data["audit"] = [
                {
                    "id": log.id,
                    "event_type": log.event_type,
                    "user_id": log.user_id,
                    "ip": log.ip,
                    "path": log.path,
                    "method": log.method,
                    "created_at": log.created_at.isoformat(),
                }
                for log in logs
            ]
        
        elif data_type == "projects":
            projects_query = db.query(Project, User.username).join(User, Project.user_id == User.id)
            if date_from:
                projects_query = projects_query.filter(Project.created_at >= date_from)
            if date_to:
                projects_query = projects_query.filter(Project.created_at <= date_to)
            projects = projects_query.all()
            data["projects"] = [
                {
                    "id": p.Project.id,
                    "name": p.Project.name,
                    "user_id": p.Project.user_id,
                    "username": p.username,
                    "created_at": p.Project.created_at.isoformat(),
                }
                for p in projects
            ]
        
        elif data_type == "memory":
            memory_query = db.query(MemoryEntry, User.username).join(User, MemoryEntry.user_id == User.id)
            if date_from:
                memory_query = memory_query.filter(MemoryEntry.created_at >= date_from)
            if date_to:
                memory_query = memory_query.filter(MemoryEntry.created_at <= date_to)
            entries = memory_query.all()
            data["memory"] = [
                {
                    "id": e.MemoryEntry.id,
                    "title": e.MemoryEntry.title,
                    "user_id": e.MemoryEntry.user_id,
                    "username": e.username,
                    "created_at": e.MemoryEntry.created_at.isoformat(),
                }
                for e in entries
            ]
        
        elif data_type == "knowledge":
            knowledge_query = db.query(KnowledgeDocument, User.username).join(User, KnowledgeDocument.user_id == User.id)
            if date_from:
                knowledge_query = knowledge_query.filter(KnowledgeDocument.created_at >= date_from)
            if date_to:
                knowledge_query = knowledge_query.filter(KnowledgeDocument.created_at <= date_to)
            docs = knowledge_query.all()
            data["knowledge"] = [
                {
                    "id": d.KnowledgeDocument.id,
                    "name": d.KnowledgeDocument.name,
                    "user_id": d.KnowledgeDocument.user_id,
                    "username": d.username,
                    "created_at": d.KnowledgeDocument.created_at.isoformat(),
                }
                for d in docs
            ]
        
        elif data_type == "diagnostics":
            # Get current diagnostics data
            registry = getattr(request.app.state, "provider_registry", None)
            db_check = await check_database(db, get_settings())
            provider_check = await check_providers(registry)
            
            data["diagnostics"] = [
                {
                    "component": "database",
                    "status": db_check["status"],
                    "latency_ms": db_check.get("latency_ms"),
                    "tables": db_check.get("tables", {}),
                },
                {
                    "component": "providers",
                    "status": provider_check["status"],
                    "total": provider_check["total"],
                    "healthy": provider_check["healthy"],
                },
            ]
        
        elif data_type == "providers":
            registry = getattr(request.app.state, "provider_registry", None)
            if registry:
                provider_check = await check_providers(registry)
                data["providers"] = [
                    {
                        "name": name,
                        "status": info["status"],
                        "healthy": info["healthy"],
                        "latency_ms": info.get("latency_ms"),
                        "models_available": info.get("models_available"),
                    }
                    for name, info in provider_check.get("providers", {}).items()
                ]
    
    return data


@router.post("/export", response_model=ExportJobResponse)
async def create_export(
    request_data: ExportRequest,
    http_request: Request,
    db: DBSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Create a new export job."""
    job_id = _generate_export_id()
    
    # Parse dates
    date_from = None
    date_to = None
    if request_data.date_from:
        date_from = datetime.fromisoformat(request_data.date_from)
    if request_data.date_to:
        date_to = datetime.fromisoformat(request_data.date_to)
    
    # Create job
    job = {
        "job_id": job_id,
        "status": "processing",
        "created_at": utcnow().isoformat(),
        "expires_at": (utcnow() + timedelta(hours=24)).isoformat(),
        "download_url": None,
        "filename": None,
        "size_bytes": None,
        "error_message": None,
    }
    _export_jobs[job_id] = job
    
    try:
        # Collect data
        raw_data = await _collect_export_data(
            db,
            request_data.data_types,
            date_from,
            date_to,
            http_request,
        )
        
        # Redact PII if requested
        if request_data.redact_pii:
            for key in raw_data:
                if isinstance(raw_data[key], list):
                    raw_data[key] = [_redact_sensitive_data(item, True) for item in raw_data[key]]
        
        # Format data
        if request_data.format == "json":
            content = json.dumps(raw_data, indent=2, default=str)
            filename = f"omniai-export-{job_id[:8]}.json"
        elif request_data.format == "csv":
            # For CSV, combine all data into sections
            content_parts = []
            for data_type, items in raw_data.items():
                if items:
                    content_parts.append(f"# {data_type.upper()}\n")
                    content_parts.append(_format_as_csv(items))
                    content_parts.append("")
            content = "\n".join(content_parts)
            filename = f"omniai-export-{job_id[:8]}.csv"
        elif request_data.format == "markdown":
            content_parts = []
            for data_type, items in raw_data.items():
                content_parts.append(_format_as_markdown(items, data_type.upper()))
                content_parts.append("")
            content = "\n\n".join(content_parts)
            filename = f"omniai-export-{job_id[:8]}.md"
        else:
            # PDF not implemented - fallback to JSON
            content = json.dumps(raw_data, indent=2, default=str)
            filename = f"omniai-export-{job_id[:8]}.json"
        
        # Store content (in production, write to S3/filesystem)
        job["content"] = content
        job["filename"] = filename
        job["size_bytes"] = len(content.encode("utf-8"))
        job["status"] = "completed"
        job["download_url"] = f"/api/admin/export/{job_id}/download"
        
        logger.info(f"Admin {admin.username} created export {job_id}")
        audit_log_event(
            db,
            event_type="admin.export_create",
            user_id=admin.id,
            request=http_request,
            data={
                "job_id": job_id,
                "format": request_data.format,
                "data_types": request_data.data_types,
            },
        )
        
    except Exception as e:
        job["status"] = "failed"
        job["error_message"] = str(e)
        logger.error(f"Export job {job_id} failed: {e}")
    
    return ExportJobResponse(**job)


@router.get("/export/{job_id}", response_model=ExportJobResponse)
async def get_export_status(
    job_id: str,
    admin: User = Depends(get_admin_user),
):
    """Get export job status."""
    job = _export_jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export job not found",
        )
    
    # Remove content from response
    response_data = {k: v for k, v in job.items() if k != "content"}
    return ExportJobResponse(**response_data)


@router.get("/export/{job_id}/download")
async def download_export(
    job_id: str,
    admin: User = Depends(get_admin_user),
):
    """Download export file."""
    job = _export_jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export job not found",
        )
    
    if job["status"] != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Export not ready",
        )
    
    content = job.get("content", "")
    filename = job.get("filename", "export.txt")
    
    # Determine content type
    content_type = "application/octet-stream"
    if filename.endswith(".json"):
        content_type = "application/json"
    elif filename.endswith(".csv"):
        content_type = "text/csv"
    elif filename.endswith(".md"):
        content_type = "text/markdown"
    
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/exports")
async def list_exports(
    admin: User = Depends(get_admin_user),
):
    """List recent export jobs."""
    jobs = [
        {k: v for k, v in job.items() if k != "content"}
        for job in _export_jobs.values()
    ]
    return {"exports": sorted(jobs, key=lambda x: x["created_at"], reverse=True)}
