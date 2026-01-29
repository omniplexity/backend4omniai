"""
Database session management.

Provides session factory and FastAPI dependency for database access.
"""

from collections.abc import Generator

from sqlalchemy.orm import Session, sessionmaker

from app.db.engine import get_engine

_session_factory: sessionmaker[Session] | None = None


def get_session_factory() -> sessionmaker[Session]:
    """
    Get or create the session factory.

    Returns cached factory instance, creating it on first call.
    """
    global _session_factory

    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.

    Yields a session and ensures it's closed after the request.

    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()
