"""
Quota repository for user quotas and usage counters.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import UsageCounter, User, UserQuota


def get_user_quota(db: Session, user_id: str) -> UserQuota | None:
    """Return quota settings for the given user."""
    return db.get(UserQuota, user_id)


def update_user_quota(
    db: Session,
    user_id: str,
    *,
    messages_per_day: int | None,
    tokens_per_day: int | None,
) -> UserQuota:
    """Upsert quota limits for a user."""
    quota = get_user_quota(db, user_id)
    if not quota:
        quota = UserQuota(user_id=user_id)
        db.add(quota)
    quota.messages_per_day = messages_per_day
    quota.tokens_per_day = tokens_per_day
    if messages_per_day is not None or tokens_per_day is not None:
        next_reset = (
            datetime.now(UTC)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=1)
        )
        quota.reset_at = next_reset
    else:
        quota.reset_at = None
    db.flush()
    return quota


def list_users_with_quota(
    db: Session, *, limit: int = 50, offset: int = 0
) -> list[User]:
    """Return paginated users with quota information."""
    stmt = (
        select(User)
        .options(selectinload(User.quota))
        .order_by(User.username)
        .limit(limit)
        .offset(offset)
    )
    return db.execute(stmt).scalars().all()


def get_usage_counter(
    db: Session, user_id: str, target_date: date | None = None
) -> UsageCounter | None:
    """Get usage counter for a specific user/date."""
    target_date = target_date or datetime.now(UTC).date()
    stmt = select(UsageCounter).where(
        UsageCounter.user_id == user_id, UsageCounter.date == target_date
    )
    return db.execute(stmt).scalar_one_or_none()


def increment_usage_counter(
    db: Session,
    user_id: str,
    *,
    messages: int = 0,
    tokens: int = 0,
    target_date: date | None = None,
) -> UsageCounter:
    """Increment usage totals for the given user/date."""
    target_date = target_date or datetime.now(UTC).date()
    counter = get_usage_counter(db, user_id, target_date)
    if not counter:
        counter = UsageCounter(user_id=user_id, date=target_date)
        db.add(counter)
    if counter.messages_used is None:
        counter.messages_used = 0
    if counter.tokens_used is None:
        counter.tokens_used = 0
    counter.messages_used += messages
    counter.tokens_used += tokens
    db.flush()
    return counter


def list_usage_entries(
    db: Session,
    *,
    start_date: date,
    end_date: date,
    limit: int = 200,
    offset: int = 0,
) -> list[UsageCounter]:
    """List usage records between the supplied dates."""
    stmt = (
        select(UsageCounter)
        .where(UsageCounter.date >= start_date, UsageCounter.date <= end_date)
        .order_by(UsageCounter.date.desc())
        .limit(limit)
        .offset(offset)
    )
    return db.execute(stmt).scalars().all()
