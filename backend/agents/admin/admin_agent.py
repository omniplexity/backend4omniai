"""Admin Agent.

Handles administrative operations: user management, invites, audit logs, and monitoring.
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session as DBSession

from backend.db.models import User, InviteCode, AuditLog, Session
from backend.core.logging import get_logger
from backend.services.audit_service import audit_log_event

logger = get_logger(__name__)


@dataclass
class UserSummary:
    """User summary for admin view."""
    id: str
    email: str
    username: str
    is_active: bool
    is_admin: bool
    created_at: datetime


@dataclass
class InviteSummary:
    """Invite code summary."""
    id: str
    code: str
    created_by: Optional[str]
    used_by: Optional[str]
    expires_at: Optional[datetime]
    created_at: datetime


@dataclass
class AuditEntry:
    """Audit log entry."""
    id: str
    user_id: Optional[str]
    event_type: str
    ip: Optional[str]
    path: Optional[str]
    method: Optional[str]
    data_json: Optional[Dict[str, Any]]
    created_at: datetime


@dataclass
class SystemStats:
    """System statistics."""
    total_users: int
    active_users: int
    admin_users: int
    unused_invites: int


class AdminAgent:
    """Agent for administrative operations."""

    def __init__(self, db: DBSession, settings: Dict[str, Any] = None):
        """Initialize the Admin Agent.
        
        Args:
            db: Database session
            settings: Optional admin settings
        """
        self.db = db
        self.settings = settings or {}

    # User Management
    
    def list_users(
        self,
        admin: User,
        limit: int = 100,
        offset: int = 0,
    ) -> List[UserSummary]:
        """List all users.
        
        Args:
            admin: Admin user making the request
            limit: Maximum results
            offset: Offset for pagination
            
        Returns:
            List of UserSummary objects
        """
        users = (
            self.db.query(User)
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        
        return [
            UserSummary(
                id=u.id,
                email=u.email,
                username=u.username,
                is_active=u.is_active,
                is_admin=u.is_admin,
                created_at=u.created_at,
            )
            for u in users
        ]

    def get_user(self, admin: User, user_id: str) -> Optional[UserSummary]:
        """Get a user by ID.
        
        Args:
            admin: Admin user making the request
            user_id: User ID to get
            
        Returns:
            UserSummary if found, None otherwise
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        
        return UserSummary(
            id=user.id,
            email=user.email,
            username=user.username,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=user.created_at,
        )

    def update_user(
        self,
        admin: User,
        user_id: str,
        is_active: Optional[bool] = None,
        is_admin: Optional[bool] = None,
    ) -> Optional[UserSummary]:
        """Update a user.
        
        Args:
            admin: Admin user making the request
            user_id: User ID to update
            is_active: New active status
            is_admin: New admin status
            
        Returns:
            Updated UserSummary or None if not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        
        # Prevent admin from demoting themselves
        if user.id == admin.id and is_admin is False:
            raise ValueError("Cannot remove your own admin status")
        
        if is_active is not None:
            user.is_active = is_active
        if is_admin is not None:
            user.is_admin = is_admin
        
        self.db.commit()
        self.db.refresh(user)
        
        logger.info(f"Admin {admin.username} updated user {user.username}")
        audit_log_event(
            self.db,
            event_type="admin.user_update",
            user_id=admin.id,
            request=None,
            data={"target_user_id": user.id, "is_active": is_active, "is_admin": is_admin},
        )
        
        return UserSummary(
            id=user.id,
            email=user.email,
            username=user.username,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=user.created_at,
        )

    def delete_user(self, admin: User, user_id: str) -> bool:
        """Delete a user.
        
        Args:
            admin: Admin user making the request
            user_id: User ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        if user_id == admin.id:
            raise ValueError("Cannot delete your own account")
        
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        self.db.delete(user)
        self.db.commit()
        
        logger.info(f"Admin {admin.username} deleted user {user.username}")
        audit_log_event(
            self.db,
            event_type="admin.user_delete",
            user_id=admin.id,
            request=None,
            data={"target_user_id": user.id, "target_username": user.username},
        )
        
        return True

    # Invite Management
    
    def create_invite(
        self,
        admin: User,
        expires_in_days: int = 7,
    ) -> InviteSummary:
        """Create an invite code.
        
        Args:
            admin: Admin creating the invite
            expires_in_days: Days until expiration
            
        Returns:
            Created InviteSummary
        """
        import secrets
        
        code = secrets.token_urlsafe(16)
        expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        
        invite = InviteCode(
            code=code,
            created_by=admin.id,
            expires_at=expires_at,
        )
        self.db.add(invite)
        self.db.commit()
        self.db.refresh(invite)
        
        logger.info(f"Admin {admin.username} created invite code")
        audit_log_event(
            self.db,
            event_type="admin.invite_create",
            user_id=admin.id,
            request=None,
            data={"invite_id": invite.id},
        )
        
        return InviteSummary(
            id=invite.id,
            code=invite.code,
            created_by=invite.created_by,
            used_by=invite.used_by,
            expires_at=invite.expires_at,
            created_at=invite.created_at,
        )

    def list_invites(self, admin: User) -> List[InviteSummary]:
        """List all invite codes.
        
        Args:
            admin: Admin listing invites
            
        Returns:
            List of InviteSummary objects
        """
        invites = (
            self.db.query(InviteCode)
            .order_by(InviteCode.created_at.desc())
            .all()
        )
        
        return [
            InviteSummary(
                id=i.id,
                code=i.code,
                created_by=i.created_by,
                used_by=i.used_by,
                expires_at=i.expires_at,
                created_at=i.created_at,
            )
            for i in invites
        ]

    def delete_invite(self, admin: User, invite_id: str) -> bool:
        """Delete an invite code.
        
        Args:
            admin: Admin deleting the invite
            invite_id: Invite ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        invite = self.db.query(InviteCode).filter(InviteCode.id == invite_id).first()
        if not invite:
            return False
        
        self.db.delete(invite)
        self.db.commit()
        
        audit_log_event(
            self.db,
            event_type="admin.invite_delete",
            user_id=admin.id,
            request=None,
            data={"invite_id": invite_id},
        )
        
        return True

    # Session Management
    
    def get_user_sessions(self, admin: User, user_id: str) -> List[Dict[str, Any]]:
        """Get sessions for a user.
        
        Args:
            admin: Admin requesting sessions
            user_id: User ID
            
        Returns:
            List of session info dicts
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return []
        
        sessions = (
            self.db.query(Session)
            .filter(Session.user_id == user_id, Session.expires_at > datetime.utcnow())
            .order_by(Session.created_at.desc())
            .all()
        )
        
        return [
            {
                "id": s.id,
                "created_at": s.created_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
            }
            for s in sessions
        ]

    def revoke_user_sessions(self, admin: User, user_id: str) -> int:
        """Revoke all sessions for a user.
        
        Args:
            admin: Admin revoking sessions
            user_id: User ID
            
        Returns:
            Number of sessions revoked
        """
        if user_id == admin.id:
            raise ValueError("Cannot revoke your own sessions")
        
        count = (
            self.db.query(Session)
            .filter(Session.user_id == user_id)
            .delete()
        )
        self.db.commit()
        
        logger.info(f"Admin {admin.username} revoked {count} sessions for user {user_id}")
        audit_log_event(
            self.db,
            event_type="admin.sessions_revoke_all",
            user_id=admin.id,
            request=None,
            data={"target_user_id": user_id, "sessions_revoked": count},
        )
        
        return count

    # Audit Logs
    
    def get_audit_logs(
        self,
        admin: User,
        event: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEntry]:
        """Get audit log entries.
        
        Args:
            admin: Admin requesting logs
            event: Optional event type filter
            from_date: Optional start date
            to_date: Optional end date
            limit: Maximum results
            offset: Offset for pagination
            
        Returns:
            List of AuditEntry objects
        """
        query = self.db.query(AuditLog).order_by(AuditLog.created_at.desc())
        
        if event:
            query = query.filter(AuditLog.event_type == event)
        if from_date:
            query = query.filter(AuditLog.created_at >= from_date)
        if to_date:
            query = query.filter(AuditLog.created_at <= to_date)
        
        entries = query.offset(offset).limit(min(500, max(1, limit))).all()
        
        return [
            AuditEntry(
                id=e.id,
                user_id=e.user_id,
                event_type=e.event_type,
                ip=e.ip,
                path=e.path,
                method=e.method,
                data_json=e.data_json,
                created_at=e.created_at,
            )
            for e in entries
        ]

    # Statistics
    
    def get_stats(self, admin: User) -> SystemStats:
        """Get system statistics.
        
        Args:
            admin: Admin requesting stats
            
        Returns:
            SystemStats object
        """
        total_users = self.db.query(User).count()
        active_users = self.db.query(User).filter(User.is_active == True).count()
        admin_users = self.db.query(User).filter(User.is_admin == True).count()
        unused_invites = (
            self.db.query(InviteCode)
            .filter(InviteCode.used_by.is_(None))
            .count()
        )
        
        return SystemStats(
            total_users=total_users,
            active_users=active_users,
            admin_users=admin_users,
            unused_invites=unused_invites,
        )
