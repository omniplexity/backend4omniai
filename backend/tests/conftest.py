"""
Pytest configuration and fixtures.
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="session")
def app():
    """Create test application instance."""
    return create_app()


@pytest.fixture(scope="session")
def client(app):
    """Create test client."""
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def chat_db_path(tmp_path_factory):
    """Run migrations on a temporary database for chat tests."""
    db_dir = tmp_path_factory.mktemp("chat-db")
    db_path = db_dir / "chat.db"
    prev_db = os.environ.get("DATABASE_URL")
    prev_cookie_secure = os.environ.get("COOKIE_SECURE")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["COOKIE_SECURE"] = "false"

    from alembic import command
    from alembic.config import Config

    from app.config import get_settings
    from app.db.engine import dispose_engine

    get_settings.cache_clear()
    dispose_engine()

    backend_dir = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    try:
        command.upgrade(alembic_cfg, "head")
        yield str(db_path)
    finally:
        dispose_engine()
        import app.db.session

        app.db.session._session_factory = None
        get_settings.cache_clear()

        if prev_db is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev_db
        if prev_cookie_secure is None:
            os.environ.pop("COOKIE_SECURE", None)
        else:
            os.environ["COOKIE_SECURE"] = prev_cookie_secure


@pytest.fixture
def chat_client(chat_db_path, monkeypatch):
    """Test client wired to the chat database."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{chat_db_path}")

    from app.config import get_settings

    get_settings.cache_clear()
    app = create_app()

    with TestClient(app) as client:
        yield client


@pytest.fixture
def chat_db_session(chat_db_path):
    """Database session bound to the chat database."""
    from app.config import get_settings
    from app.db import get_db

    get_settings.cache_clear()
    db_gen = get_db()
    session = next(db_gen)
    try:
        yield session
    finally:
        db_gen.close()
