from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from backend.app.auth.audit import write_audit
from backend.app.auth.csrf import require_csrf
from backend.app.auth.password import hash_password, verify_password
from backend.app.auth.sessions import create_session, delete_session
from backend.app.config.settings import settings
from backend.app.db.models import User
from backend.app.db.repo.invites_repo import consume_invite, get_invite
from backend.app.db.repo.users_repo import create_user, get_user_by_username
from backend.app.db.session import get_db
from backend.app.auth.deps import require_active_user, get_current_user
from backend.app.services.rate_limit import rate_limiter

router = APIRouter(prefix="/auth", tags=["auth"])


def check_ip_rate_limit(request: Request) -> None:
    """Check IP rate limit for auth endpoints."""
    client_ip = request.client.host if request.client else "unknown"
    rate_limiter.check_ip_rate(client_ip)


class RegisterRequest(BaseModel):
    invite_code: str
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/register")
def register(request: Request, body: RegisterRequest, db: Session = Depends(get_db)) -> JSONResponse:
    # Check IP rate limit
    check_ip_rate_limit(request)

    if settings.invite_only:
        invite = get_invite(db, body.invite_code)
        if not invite or invite.used_by or invite.revoked_at or invite.expires_at < datetime.now(timezone.utc):
            write_audit(db, None, "REGISTER_FAILED", f"invite:{body.invite_code}", request)
            db.commit()
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_INVITE", "message": "Invalid or expired invite code"},
            )

    if get_user_by_username(db, body.username):
        raise HTTPException(status_code=409, detail={"code": "USERNAME_EXISTS", "message": "Username already exists"})

    user = create_user(db, username=body.username, password_hash=hash_password(body.password))
    if settings.invite_only:
        consume_invite(db, body.invite_code, user.id)
        write_audit(db, user.id, "INVITE_CONSUMED", f"invite:{body.invite_code}", request)

    session_id, csrf_token = create_session(db, user.id, device_meta=request.headers.get("User-Agent"))
    write_audit(db, user.id, "REGISTER_SUCCESS", f"user:{user.id}", request)

    db.commit()

    resp = JSONResponse(
        content={"user": {"id": user.id, "username": user.username, "role": user.role, "status": user.status},
                 "csrf_token": csrf_token}
    )
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


@router.post("/login")
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)) -> JSONResponse:
    # Check IP rate limit
    check_ip_rate_limit(request)

    user = get_user_by_username(db, body.username)
    if not user or not verify_password(body.password, user.password_hash):
        write_audit(db, None, "LOGIN_FAILED", f"username:{body.username}", request)
        db.commit()
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_CREDENTIALS", "message": "Invalid username or password"},
        )

    if user.status != "active":
        raise HTTPException(status_code=401, detail={"code": "USER_INACTIVE", "message": "Account is inactive"})

    user.last_login = datetime.now(timezone.utc)
    session_id, csrf_token = create_session(db, user.id, device_meta=request.headers.get("User-Agent"))
    write_audit(db, user.id, "LOGIN_SUCCESS", f"user:{user.id}", request)

    db.commit()

    resp = JSONResponse(
        content={"user": {"id": user.id, "username": user.username, "role": user.role, "status": user.status},
                 "csrf_token": csrf_token}
    )
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


@router.post("/logout", dependencies=[Depends(require_csrf)])
def logout(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    user = get_current_user(request, db)
    # Check rate limits
    check_ip_rate_limit(request)
    rate_limiter.check_user_rate(user.id)

    session_id = request.cookies.get(settings.session_cookie_name) or ""
    delete_session(db, session_id)
    write_audit(db, user.id, "LOGOUT", f"user:{user.id}", request)
    db.commit()

    resp = JSONResponse(content={"message": "Logged out successfully"})
    resp.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=str(settings.cookie_samesite).lower(),
        path="/",
    )
    return resp


@router.get("/me")
def me(user: User = Depends(require_active_user)) -> dict:
    return {"user": {"id": user.id, "username": user.username, "role": user.role, "status": user.status}}