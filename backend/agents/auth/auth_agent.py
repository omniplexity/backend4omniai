"""Auth Agent.

Manages user authentication, sessions, CSRF tokens, and invite codes.
Provides registration, login, logout, and session management.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session as DBSession
from fastapi import Request, HTTPException, status

from backend.config import Settings
from backend.db.models import User, Session as SessionModel, InviteCode
from backend.auth.password import hash_password, validate_password_complexity, verify_password
from backend.auth.session import create_session, validate_session, invalidate_session, rotate_session
from backend.core.time import utcnow
from backend.core.logging import get_logger
from backend.services.audit_service import audit_log_event

logger = get_logger(__name__)


@dataclass
class UserInfo:
    """User information."""
    id: str
    email: str
    username: str
    is_admin: bool
    is_active: bool
    created_at: datetime


@dataclass
class SessionInfo:
    """Session information."""
    id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    is_current: bool = False


@dataclass
class AuthResult:
    """Authentication result."""
    user: UserInfo
    session_token: str
    csrf_token: str


class AuthAgent:
    """Agent for managing authentication."""

    def __init__(self, settings: Settings):
        """Initialize the Auth Agent.
        
        Args:
            settings: Application settings
        """
        self.settings = settings

    def register(
        self,
        db: DBSession,
        email: str,
        username: str,
        password: str,
        invite_code: Optional[str] = None,
        request: Request = None
    ) -> AuthResult:
        """Register a new user.
        
        Args:
            db: Database session
            email: User email
            username: Username
            password: Plain text password
            invite_code: Optional invite code
            request: HTTP request for audit logging
            
        Returns:
            AuthResult with user and session tokens
            
        Raises:
            HTTPException: If registration fails
        """
        # Validate password complexity
        password_error = validate_password_complexity(password)
        if password_error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=password_error
            )

        # Check invite requirement
        if self.settings.invite_required and not invite_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invite code required"
            )

        # Validate invite code
        invite = None
        if self.settings.invite_required and invite_code:
            invite = db.query(InviteCode).filter(
                InviteCode.code == invite_code,
                InviteCode.used_by.is_(None),
            ).first()
            if not invite:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or used invite code"
                )
            if invite.expires_at and invite.expires_at < utcnow():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invite code expired"
                )

        # Check for existing user
        existing = db.query(User).filter(
            (User.email == email) | (User.username == username)
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username or email already exists"
            )

        # Create user
        user = User(
            email=email,
            username=username,
            hashed_password=hash_password(password),
        )
        db.add(user)
        db.flush()

        # Mark invite as used
        if invite:
            invite.used_by = user.id
            invite.used_at = utcnow()

        db.commit()
        db.refresh(user)

        # Audit log
        if request:
            audit_log_event(
                db,
                event_type="auth.register",
                user_id=user.id,
                request=request,
                data={"username": user.username}
            )

        # Create session
        session_token, csrf_token = create_session(db, user)

        return AuthResult(
            user=UserInfo(
                id=user.id,
                email=user.email,
                username=user.username,
                is_admin=user.is_admin,
                is_active=user.is_active,
                created_at=user.created_at,
            ),
            session_token=session_token,
            csrf_token=csrf_token,
        )

    def login(
        self,
        db: DBSession,
        username: str,
        password: str,
        request: Request = None
    ) -> AuthResult:
        """Login with username and password.
        
        Args:
            db: Database session
            username: Username
            password: Plain text password
            request: HTTP request for audit logging
            
        Returns:
            AuthResult with user and session tokens
            
        Raises:
            HTTPException: If login fails
        """
        # Find user
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        # Verify password
        if not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled"
            )

        # Create session
        session_token, csrf_token = create_session(db, user)

        # Audit log
        if request:
            audit_log_event(
                db,
                event_type="auth.login",
                user_id=user.id,
                request=request,
                data={"username": user.username}
            )

        return AuthResult(
            user=UserInfo(
                id=user.id,
                email=user.email,
                username=user.username,
                is_admin=user.is_admin,
                is_active=user.is_active,
                created_at=user.created_at,
            ),
            session_token=session_token,
            csrf_token=csrf_token,
        )

    def logout(
        self,
        db: DBSession,
        session_token: str,
        request: Request = None
    ) -> None:
        """Logout and invalidate session.
        
        Args:
            db: Database session
            session_token: Session token to invalidate
            request: HTTP request for audit logging
        """
        user_id = None
        if session_token:
            session = validate_session(db, session_token)
            if session:
                user_id = session.user_id
            invalidate_session(db, session_token)

        # Audit log
        if request and user_id:
            audit_log_event(
                db,
                event_type="auth.logout",
                user_id=user_id,
                request=request,
                data=None
            )

    def validate_session(self, db: DBSession, session_token: str) -> Optional[UserInfo]:
        """Validate a session token.
        
        Args:
            db: Database session
            session_token: Session token to validate
            
        Returns:
            UserInfo if valid, None otherwise
        """
        session = validate_session(db, session_token)
        if not session:
            return None

        user = db.query(User).filter(User.id == session.user_id).first()
        if not user or not user.is_active:
            return None

        return UserInfo(
            id=user.id,
            email=user.email,
            username=user.username,
            is_admin=user.is_admin,
            is_active=user.is_active,
            created_at=user.created_at,
        )

    def refresh_session(
        self,
        db: DBSession,
        session_token: str,
        request: Request = None
    ) -> AuthResult:
        """Rotate session and CSRF tokens.
        
        Args:
            db: Database session
            session_token: Current session token
            request: HTTP request for audit logging
            
        Returns:
            AuthResult with new tokens
            
        Raises:
            HTTPException: If session is invalid
        """
        existing = validate_session(db, session_token)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or invalid"
            )

        user = db.query(User).filter(User.id == existing.user_id).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        rotated = rotate_session(db, session_token)
        if not rotated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or invalid"
            )
        new_session_token, new_csrf_token, _ = rotated

        # Audit log
        if request:
            audit_log_event(
                db,
                event_type="auth.refresh",
                user_id=user.id,
                request=request,
                data={"username": user.username}
            )

        return AuthResult(
            user=UserInfo(
                id=user.id,
                email=user.email,
                username=user.username,
                is_admin=user.is_admin,
                is_active=user.is_active,
                created_at=user.created_at,
            ),
            session_token=new_session_token,
            csrf_token=new_csrf_token,
        )

    def create_invite(
        self,
        db: DBSession,
        created_by: User,
        expires_in_days: int = 7,
        request: Request = None
    ) -> InviteCode:
        """Create an invite code.
        
        Args:
            db: Database session
            created_by: User creating the invite
            expires_in_days: Days until expiration
            request: HTTP request for audit logging
            
        Returns:
            Created InviteCode
        """
        import secrets
        from datetime import timedelta

        code = secrets.token_urlsafe(16)
        expires_at = utcnow() + timedelta(days=expires_in_days)

        invite = InviteCode(
            code=code,
            created_by=created_by.id,
            expires_at=expires_at,
        )
        db.add(invite)
        db.commit()
        db.refresh(invite)

        # Audit log
        if request:
            audit_log_event(
                db,
                event_type="admin.invite_create",
                user_id=created_by.id,
                request=request,
                data={"invite_id": invite.id}
            )

        return invite

    def validate_invite(
        self,
        db: DBSession,
        code: str
    ) -> Optional[InviteCode]:
        """Validate an invite code.
        
        Args:
            db: Database session
            code: Invite code to validate
            
        Returns:
            InviteCode if valid, None otherwise
        """
        invite = db.query(InviteCode).filter(
            InviteCode.code == code,
            InviteCode.used_by.is_(None),
        ).first()
        
        if not invite:
            return None
            
        if invite.expires_at and invite.expires_at < utcnow():
            return None
            
        return invite

    def list_sessions(
        self,
        db: DBSession,
        user: User,
        current_session_token: str = None
    ) -> List[SessionInfo]:
        """List active sessions for a user.
        
        Args:
            db: Database session
            user: User to list sessions for
            current_session_token: Current session token to mark as current
            
        Returns:
            List of SessionInfo
        """
        from backend.auth.session import hash_session_token
        
        current_hash = None
        if current_session_token:
            current_hash = hash_session_token(current_session_token)

        sessions = (
            db.query(SessionModel)
            .filter(SessionModel.user_id == user.id, SessionModel.expires_at > utcnow())
            .order_by(SessionModel.created_at.desc())
            .all()
        )
        
        return [
            SessionInfo(
                id=s.id,
                user_id=s.user_id,
                created_at=s.created_at,
                expires_at=s.expires_at,
                is_current=(current_hash == s.token_hash) if current_hash else False,
            )
            for s in sessions
        ]

    def revoke_session(
        self,
        db: DBSession,
        session_id: str,
        user: User,
        request: Request = None
    ) -> bool:
        """Revoke a session.
        
        Args:
            db: Database session
            session_id: Session ID to revoke
            user: User revoking (for audit)
            request: HTTP request for audit logging
            
        Returns:
            True if revoked, False if not found
        """
        from backend.auth.session import hash_session_token
        
        session = db.query(SessionModel).filter(
            SessionModel.id == session_id,
            SessionModel.user_id == user.id
        ).first()
        
        if not session:
            return False

        db.delete(session)
        db.commit()

        # Audit log
        if request:
            audit_log_event(
                db,
                event_type="auth.session_revoke",
                user_id=user.id,
                request=request,
                data={"session_id": session_id}
            )

        return True
