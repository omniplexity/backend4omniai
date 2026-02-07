"""Bootstrap admin user from environment variables."""

from sqlalchemy.orm import sessionmaker

from backend.auth.password import hash_password
from backend.config import Settings
from backend.core.logging import get_logger
from backend.db.database import get_engine
from backend.db.models import User

logger = get_logger(__name__)


def ensure_bootstrap_admin(settings: Settings) -> None:
    """Create an admin user from env vars if none exists."""
    if not settings.bootstrap_admin_enabled:
        return

    username = (settings.bootstrap_admin_username or "").strip()
    email = (settings.bootstrap_admin_email or "").strip()
    password = settings.bootstrap_admin_password or ""

    if not username or not email or not password:
        logger.warning(
            "Bootstrap admin enabled but missing required env vars",
            data={
                "username_set": bool(username),
                "email_set": bool(email),
                "password_set": bool(password),
            },
        )
        return

    engine = get_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        existing_admin = db.query(User).filter(User.is_admin == True).first()
        if existing_admin:
            return

        conflict = db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()
        if conflict:
            logger.warning(
                "Bootstrap admin skipped; user with username/email already exists",
                data={"username": username, "email": email},
            )
            return

        admin = User(
            email=email,
            username=username,
            hashed_password=hash_password(password),
            is_admin=True,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        logger.warning(
            "Bootstrap admin created",
            data={"username": username, "email": email},
        )
    finally:
        db.close()
