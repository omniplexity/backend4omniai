"""
Database engine configuration.

Creates SQLAlchemy engine with appropriate settings for SQLite or PostgreSQL.
"""

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import get_settings
from app.core import get_logger

logger = get_logger(__name__)

_engine: Engine | None = None


def get_engine() -> Engine:
    """
    Get or create the database engine.

    Returns cached engine instance, creating it on first call.
    Handles SQLite-specific configuration (connect_args, directory creation).
    """
    global _engine

    if _engine is not None:
        return _engine

    settings = get_settings()
    database_url = settings.database_url

    # SQLite-specific configuration
    if settings.is_sqlite:
        # Ensure data directory exists for SQLite
        db_path = database_url.replace("sqlite:///", "")
        if db_path.startswith("./"):
            db_path = db_path[2:]
        db_dir = Path(db_path).parent
        if db_dir and not db_dir.exists():
            db_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created database directory: {db_dir}")

        _engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},  # Required for SQLite + threads
            echo=settings.debug,
            pool_pre_ping=True,
        )
    else:
        # PostgreSQL or other databases
        _engine = create_engine(
            database_url,
            echo=settings.debug,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )

    logger.info(
        "Database engine created",
        data={"dialect": _engine.dialect.name, "debug": settings.debug},
    )

    return _engine


def verify_database_connection() -> bool:
    """
    Verify database connectivity with a simple query.

    Returns:
        True if connection successful, False otherwise.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


def dispose_engine() -> None:
    """Dispose of the engine and release all connections."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
        logger.info("Database engine disposed")
