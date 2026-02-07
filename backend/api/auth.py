"""Authentication API endpoints."""

from datetime import datetime
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session as DBSession

from backend.auth.dependencies import get_current_user, get_optional_user
from backend.auth.login_limiter import get_ip_limiter, get_username_limiter
from backend.auth.password import hash_password, validate_password_complexity, verify_password_with_upgrade
from backend.auth.session import create_session, invalidate_session, rotate_session, validate_session
from backend.config import get_settings
from backend.core.time import utcnow
from backend.core.logging import get_logger
from backend.db import get_db
from backend.db.models import (
    Artifact,
    ContextBlock,
    Conversation,
    InviteCode,
    KnowledgeChunk,
    KnowledgeDocument,
    MemoryEntry,
    Message,
    Project,
    User,
)
from backend.services.audit_service import audit_log_event

logger = get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    """Registration request model."""

    email: EmailStr
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    invite_code: Optional[str] = None


class LoginRequest(BaseModel):
    """Login request model."""

    username: str
    password: str


class UserResponse(BaseModel):
    """User response model."""

    id: str
    email: str
    username: str
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    """Authentication response model."""

    user: UserResponse
    csrf_token: str


class CsrfResponse(BaseModel):
    csrf_token: str


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class SessionInfoResponse(BaseModel):
    id: str
    created_at: datetime
    expires_at: datetime
    is_current: bool


@router.post("/register", response_model=AuthResponse)
async def register(
    payload: RegisterRequest,
    response: Response,
    http_request: Request,
    db: DBSession = Depends(get_db),
):
    """Register a new user account."""
    settings = get_settings()

    # Validate password complexity
    password_error = validate_password_complexity(payload.password)
    if password_error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=password_error,
        )

    # Check if invite code is required
    if settings.invite_required:
        if not payload.invite_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invite code required",
            )

        # Validate invite code
        invite = db.query(InviteCode).filter(
            InviteCode.code == payload.invite_code,
            InviteCode.used_by.is_(None),
        ).first()

        if not invite:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or used invite code",
            )

        if invite.expires_at and invite.expires_at < utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invite code expired",
            )

    # Check for existing user
    existing = db.query(User).filter(
        (User.email == payload.email) | (User.username == payload.username)
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration failed",
        )

    # Create user
    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.flush()

    # Mark invite as used
    if settings.invite_required and invite:
        invite.used_by = user.id
        invite.used_at = utcnow()

    db.commit()
    db.refresh(user)

    audit_log_event(
        db,
        event_type="auth.register",
        user_id=user.id,
        request=http_request,
        data={"username": user.username, "invite_required": settings.invite_required},
    )

    # Create session
    session_token, csrf_token = create_session(db, user)

    # Set session cookie
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain or None,
        path="/",
        max_age=settings.session_ttl_seconds,
    )

    # Set CSRF cookie
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain or None,
        path="/",
        max_age=settings.session_ttl_seconds,
    )

    logger.info(f"User registered: {user.username}")

    return AuthResponse(
        user=UserResponse.model_validate(user),
        csrf_token=csrf_token,
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    http_request: Request,
    db: DBSession = Depends(get_db),
):
    """Log in with username and password."""
    settings = get_settings()

    # Determine client IP for rate limiting
    forwarded_for = http_request.headers.get("x-forwarded-for", "")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else None
    if not client_ip and http_request.client:
        client_ip = http_request.client.host
    client_ip = client_ip or "unknown"

    username_limiter = get_username_limiter()
    ip_limiter = get_ip_limiter()

    # Check lockouts before doing any work
    if username_limiter.is_locked(payload.username):
        secs = username_limiter.remaining_lockout_seconds(payload.username)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(secs)},
        )

    if ip_limiter.is_locked(client_ip):
        secs = ip_limiter.remaining_lockout_seconds(client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(secs)},
        )

    # Find user
    user = db.query(User).filter(User.username == payload.username).first()

    verify = None
    if user:
        verify = verify_password_with_upgrade(payload.password, user.hashed_password)

    if not user or not verify or not verify.ok:
        # Record failures for lockout tracking
        username_limiter.record_failure(payload.username)
        ip_limiter.record_failure(client_ip)

        audit_log_event(
            db,
            event_type="auth.login_failed",
            user_id=user.id if user else None,
            request=http_request,
            data={"username": payload.username},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Clear failure counters on success
    username_limiter.record_success(payload.username)
    ip_limiter.record_success(client_ip)

    # Upgrade password hash (bcrypt -> argon2id, or argon2 parameter rehash).
    if verify.upgraded_hash:
        user.hashed_password = verify.upgraded_hash
        db.add(user)
        db.commit()

    # Create session
    session_token, csrf_token = create_session(db, user)

    # Set cookies
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain or None,
        path="/",
        max_age=settings.session_ttl_seconds,
    )

    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain or None,
        path="/",
        max_age=settings.session_ttl_seconds,
    )

    logger.info(f"User logged in: {user.username}")
    audit_log_event(
        db,
        event_type="auth.login",
        user_id=user.id,
        request=http_request,
        data={"username": user.username},
    )

    return AuthResponse(
        user=UserResponse.model_validate(user),
        csrf_token=csrf_token,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
):
    """Log out and invalidate session."""
    settings = get_settings()

    session_token = request.cookies.get(settings.session_cookie_name)
    user_id = None
    if session_token:
        session = validate_session(db, session_token)
        if session:
            user_id = session.user_id
        invalidate_session(db, session_token)

    audit_log_event(db, event_type="auth.logout", user_id=user_id, request=request, data=None)

    # Clear cookies
    response.delete_cookie(
        settings.session_cookie_name,
        domain=settings.cookie_domain or None,
        path="/",
    )
    response.delete_cookie(
        settings.csrf_cookie_name,
        domain=settings.cookie_domain or None,
        path="/",
    )

    return {"message": "Logged out"}


@router.post("/refresh", response_model=AuthResponse)
async def refresh_session(
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
):
    """Rotate session + CSRF token for an authenticated user."""
    settings = get_settings()

    session_token = request.cookies.get(settings.session_cookie_name)
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    existing = validate_session(db, session_token)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == existing.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    rotated = rotate_session(db, session_token)
    if not rotated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")
    new_session_token, new_csrf_token, _ = rotated

    response.set_cookie(
        key=settings.session_cookie_name,
        value=new_session_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain or None,
        path="/",
        max_age=settings.session_ttl_seconds,
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=new_csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain or None,
        path="/",
        max_age=settings.session_ttl_seconds,
    )

    audit_log_event(
        db,
        event_type="auth.refresh",
        user_id=user.id,
        request=request,
        data={"username": user.username},
    )

    return AuthResponse(user=UserResponse.model_validate(user), csrf_token=new_csrf_token)


@router.get("/csrf", response_model=CsrfResponse)
async def get_csrf_token(
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
):
    """Return current CSRF token for an active session (cross-origin friendly)."""
    settings = get_settings()

    session_token = request.cookies.get(settings.session_cookie_name)
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session = validate_session(db, session_token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    csrf_token = session.csrf_token

    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain or None,
        path="/",
        max_age=settings.session_ttl_seconds,
    )
    response.headers["Cache-Control"] = "no-store"
    return CsrfResponse(csrf_token=csrf_token)


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    """Get current user info."""
    return UserResponse.model_validate(current_user)


@router.get("/export")
async def export_my_data(
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export the current user's data (privacy feature).

    This intentionally excludes secrets:
    - password hash
    - session token hashes / CSRF tokens
    """
    # Conversations + messages
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.created_at.asc())
        .all()
    )
    convo_ids = [c.id for c in conversations]
    messages = []
    if convo_ids:
        messages = (
            db.query(Message)
            .filter(Message.conversation_id.in_(convo_ids))
            .order_by(Message.created_at.asc())
            .all()
        )

    memory = (
        db.query(MemoryEntry)
        .filter(MemoryEntry.user_id == current_user.id)
        .order_by(MemoryEntry.created_at.asc())
        .all()
    )

    knowledge_docs = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.user_id == current_user.id)
        .order_by(KnowledgeDocument.created_at.asc())
        .all()
    )
    doc_ids = [d.id for d in knowledge_docs]
    knowledge_chunks = []
    if doc_ids:
        knowledge_chunks = (
            db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.doc_id.in_(doc_ids))
            .order_by(KnowledgeChunk.doc_id.asc(), KnowledgeChunk.chunk_index.asc())
            .all()
        )

    projects = (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.created_at.asc())
        .all()
    )
    context_blocks = (
        db.query(ContextBlock)
        .filter(ContextBlock.user_id == current_user.id)
        .order_by(ContextBlock.created_at.asc())
        .all()
    )
    artifacts = (
        db.query(Artifact)
        .filter(Artifact.user_id == current_user.id)
        .order_by(Artifact.created_at.asc())
        .all()
    )

    audit_log_event(
        db,
        event_type="auth.export",
        user_id=current_user.id,
        request=request,
        data={"username": current_user.username},
    )

    return {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "username": current_user.username,
            "is_admin": current_user.is_admin,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        },
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "provider": c.provider,
                "model": c.model,
                "settings_json": c.settings_json,
                "system_prompt": c.system_prompt,
                "preset_id": c.preset_id,
                "project_id": c.project_id,
                "parent_conversation_id": c.parent_conversation_id,
                "branched_from_message_id": c.branched_from_message_id,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in conversations
        ],
        "messages": [
            {
                "id": m.id,
                "conversation_id": m.conversation_id,
                "role": m.role,
                "content": m.content,
                "content_parts_json": m.content_parts_json,
                "citations_json": m.citations_json,
                "tool_events_json": m.tool_events_json,
                "provider_meta_json": m.provider_meta_json,
                "provider": m.provider,
                "model": m.model,
                "tokens_prompt": m.tokens_prompt,
                "tokens_completion": m.tokens_completion,
                "parent_message_id": m.parent_message_id,
                "revision_of_message_id": m.revision_of_message_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
        "memory": [
            {
                "id": e.id,
                "title": e.title,
                "content": e.content,
                "tags": e.tags,
                "embedding_model": e.embedding_model,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "updated_at": e.updated_at.isoformat() if e.updated_at else None,
            }
            for e in memory
        ],
        "knowledge": {
            "docs": [
                {
                    "id": d.id,
                    "name": d.name,
                    "mime_type": d.mime_type,
                    "size": d.size,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in knowledge_docs
            ],
            "chunks": [
                {
                    "id": ch.id,
                    "doc_id": ch.doc_id,
                    "chunk_index": ch.chunk_index,
                    "content": ch.content,
                    "embedding_model": ch.embedding_model,
                    "created_at": ch.created_at.isoformat() if ch.created_at else None,
                }
                for ch in knowledge_chunks
            ],
        },
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "instructions": p.instructions,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in projects
        ],
        "context_blocks": [
            {
                "id": b.id,
                "project_id": b.project_id,
                "conversation_id": b.conversation_id,
                "title": b.title,
                "content": b.content,
                "enabled": b.enabled,
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "updated_at": b.updated_at.isoformat() if b.updated_at else None,
            }
            for b in context_blocks
        ],
        "artifacts": [
            {
                "id": a.id,
                "project_id": a.project_id,
                "conversation_id": a.conversation_id,
                "type": a.type,
                "title": a.title,
                "content": a.content,
                "language": a.language,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            }
            for a in artifacts
        ],
    }


@router.post("/delete")
async def delete_my_account(
    payload: DeleteAccountRequest,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete the current user's account (irreversible)."""
    verify = verify_password_with_upgrade(payload.password, current_user.hashed_password)
    if not verify.ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")

    settings = get_settings()
    session_token = request.cookies.get(settings.session_cookie_name)
    if session_token:
        invalidate_session(db, session_token)

    audit_log_event(
        db,
        event_type="auth.delete_account",
        user_id=current_user.id,
        request=request,
        data={"username": current_user.username},
    )

    # Delete user (cascades for most user-owned tables via FK ondelete).
    db.delete(current_user)
    db.commit()

    response.delete_cookie(settings.session_cookie_name, domain=settings.cookie_domain or None, path="/")
    response.delete_cookie(settings.csrf_cookie_name, domain=settings.cookie_domain or None, path="/")

    return {"message": "Account deleted"}


@router.get("/sessions", response_model=list[SessionInfoResponse])
async def list_my_sessions(
    request: Request,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List active sessions for the current user (no secrets)."""
    from backend.db.models import Session as SessionRow
    from backend.auth.session import hash_session_token

    settings = get_settings()
    session_token = request.cookies.get(settings.session_cookie_name) or ""
    current_hash = hash_session_token(session_token) if session_token else None

    rows = (
        db.query(SessionRow)
        .filter(SessionRow.user_id == current_user.id, SessionRow.expires_at > utcnow())
        .order_by(SessionRow.created_at.desc())
        .all()
    )
    return [
        SessionInfoResponse(
            id=s.id,
            created_at=s.created_at,
            expires_at=s.expires_at,
            is_current=(current_hash == s.token_hash) if current_hash else False,
        )
        for s in rows
    ]


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke one session by id (current user only)."""
    from backend.db.models import Session as SessionRow
    from backend.auth.session import hash_session_token

    settings = get_settings()
    row = (
        db.query(SessionRow)
        .filter(SessionRow.id == session_id, SessionRow.user_id == current_user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    # If the revoked session is the current one, also clear cookies.
    session_token = request.cookies.get(settings.session_cookie_name) or ""
    current_hash = hash_session_token(session_token) if session_token else None
    is_current = bool(current_hash and current_hash == row.token_hash)

    db.delete(row)
    db.commit()

    audit_log_event(
        db,
        event_type="auth.session_revoke",
        user_id=current_user.id,
        request=request,
        data={"session_id": session_id, "is_current": is_current},
    )

    if is_current:
        response.delete_cookie(settings.session_cookie_name, domain=settings.cookie_domain or None, path="/")
        response.delete_cookie(settings.csrf_cookie_name, domain=settings.cookie_domain or None, path="/")

    return {"message": "Session revoked", "session_id": session_id, "is_current": is_current}


@router.post("/sessions/revoke_all")
async def revoke_all_sessions_except_current(
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revoke all sessions for the current user except the current session."""
    from backend.db.models import Session as SessionRow
    from backend.auth.session import hash_session_token

    settings = get_settings()
    session_token = request.cookies.get(settings.session_cookie_name) or ""
    current_hash = hash_session_token(session_token) if session_token else None

    q = db.query(SessionRow).filter(SessionRow.user_id == current_user.id)
    rows = q.all()
    deleted = 0
    for s in rows:
        if current_hash and s.token_hash == current_hash:
            continue
        db.delete(s)
        deleted += 1
    db.commit()

    audit_log_event(
        db,
        event_type="auth.session_revoke_all",
        user_id=current_user.id,
        request=request,
        data={"deleted": deleted},
    )

    # If there is no current session token, clear cookies anyway.
    if not current_hash:
        response.delete_cookie(settings.session_cookie_name, domain=settings.cookie_domain or None, path="/")
        response.delete_cookie(settings.csrf_cookie_name, domain=settings.cookie_domain or None, path="/")

    return {"message": "Sessions revoked", "deleted": deleted}


@router.get("/check")
async def check_auth(
    current_user: Optional[User] = Depends(get_optional_user),
):
    """Check if user is authenticated."""
    if current_user:
        return {
            "authenticated": True,
            "user": UserResponse.model_validate(current_user),
        }
    return {"authenticated": False, "user": None}
