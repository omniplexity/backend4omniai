from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.db.models import UserQuota, UserUsageDaily


def get_or_create_quota(db: Session, user_id: int) -> UserQuota:
    """Get or create quota for user with defaults."""
    quota = db.query(UserQuota).filter(UserQuota.user_id == user_id).first()
    if not quota:
        quota = UserQuota(user_id=user_id)
        db.add(quota)
        db.flush()  # Get the ID
    return quota


def _get_today_str() -> str:
    """Get today's date in YYYY-MM-DD format (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def check_message_quota(db: Session, user_id: int, day: Optional[str] = None) -> None:
    """Check if user can send another message today. Raises HTTPException if quota exceeded."""
    from backend.app.config.settings import settings
    if settings.environment == 'test':
        return
    if day is None:
        day = _get_today_str()

    quota = get_or_create_quota(db, user_id)
    usage = db.query(UserUsageDaily).filter(
        UserUsageDaily.user_id == user_id,
        UserUsageDaily.day == day
    ).first()

    if usage and usage.messages_used >= quota.messages_per_day:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=429,
            detail={"code": "QUOTA_EXCEEDED", "message": "Daily message quota exceeded"}
        )


def increment_message_usage(db: Session, user_id: int, day: Optional[str] = None, delta: int = 1) -> None:
    """Increment message usage for user on given day."""
    if day is None:
        day = _get_today_str()

    usage = db.query(UserUsageDaily).filter(
        UserUsageDaily.user_id == user_id,
        UserUsageDaily.day == day
    ).first()

    if not usage:
        usage = UserUsageDaily(user_id=user_id, day=day, messages_used=0, tokens_used=0)
        db.add(usage)

    usage.messages_used += delta
    db.flush()


def add_token_usage(db: Session, user_id: int, tokens_delta: int, day: Optional[str] = None) -> None:
    """Add token usage for user on given day."""
    if day is None:
        day = _get_today_str()

    usage = db.query(UserUsageDaily).filter(
        UserUsageDaily.user_id == user_id,
        UserUsageDaily.day == day
    ).first()

    if not usage:
        usage = UserUsageDaily(user_id=user_id, day=day, messages_used=0, tokens_used=0)
        db.add(usage)

    usage.tokens_used += tokens_delta
    db.flush()