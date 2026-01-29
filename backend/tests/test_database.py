"""
Tests for database functionality.

Tests Alembic migrations, model definitions, and database connectivity.
"""

import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.config import Settings


@pytest.fixture(scope="module")
def temp_db_path():
    """Create a temporary database file path."""
    # Use a named temp file that persists - Windows cleanup issue with SQLite
    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test.db"
    yield str(db_path)
    # Don't try to clean up - Windows may have file locked
    # The temp dir will be cleaned up by the OS eventually


@pytest.fixture(scope="module")
def test_settings(temp_db_path):
    """Create test settings with temporary database."""
    return Settings(
        database_url=f"sqlite:///{temp_db_path}",
        debug=True,
        secret_key="test-secret-key-for-testing-only",
    )


@pytest.fixture(scope="module")
def monkeypatch_module():
    """Module-scoped monkeypatch fixture."""
    from _pytest.monkeypatch import MonkeyPatch

    m = MonkeyPatch()
    yield m
    m.undo()


@pytest.fixture(scope="module")
def migrated_db(temp_db_path, test_settings, monkeypatch_module):
    """
    Run Alembic migrations on temporary database.

    Returns the database path after migrations are complete.
    """
    # Patch settings to use temp database
    monkeypatch_module.setenv("DATABASE_URL", f"sqlite:///{temp_db_path}")

    # Clear cached settings and engine
    from app.config import get_settings
    from app.db.engine import dispose_engine

    get_settings.cache_clear()
    dispose_engine()

    # Get alembic config
    backend_dir = Path(__file__).parent.parent
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Run migrations
    command.upgrade(alembic_cfg, "head")

    yield temp_db_path

    # Cleanup: dispose engine to release file lock
    dispose_engine()

    # Also clear the session factory
    import app.db.session

    app.db.session._session_factory = None

    # Clear cached settings
    get_settings.cache_clear()


@pytest.fixture(scope="module")
def db_client(migrated_db, monkeypatch_module):
    """Create test client with migrated database."""
    # Ensure settings use migrated database
    monkeypatch_module.setenv("DATABASE_URL", f"sqlite:///{migrated_db}")

    from app.config import get_settings

    get_settings.cache_clear()

    # Import and create app after patching
    from app.main import create_app

    app = create_app()

    with TestClient(app) as client:
        yield client


class TestAlembicMigrations:
    """Test Alembic migration functionality."""

    def test_migrations_create_all_tables(self, migrated_db):
        """Verify all expected tables are created by migrations."""
        from app.db import get_engine

        engine = get_engine()
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        expected_tables = {
            "users",
            "sessions",
            "invites",
            "conversations",
            "messages",
            "audit_log",
            "alembic_version",
        }

        assert expected_tables.issubset(set(tables)), (
            f"Missing tables: {expected_tables - set(tables)}"
        )

    def test_users_table_has_correct_columns(self, migrated_db):
        """Verify users table has expected columns."""
        from app.db import get_engine

        engine = get_engine()
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("users")}

        expected_columns = {
            "id",
            "username",
            "email",
            "password_hash",
            "role",
            "status",
            "last_login",
            "created_at",
            "updated_at",
        }

        assert expected_columns.issubset(columns), (
            f"Missing columns in users: {expected_columns - columns}"
        )

    def test_messages_table_has_correct_columns(self, migrated_db):
        """Verify messages table has expected columns."""
        from app.db import get_engine

        engine = get_engine()
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("messages")}

        expected_columns = {
            "id",
            "conversation_id",
            "role",
            "content",
            "created_at",
            "provider",
            "model",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        }

        assert expected_columns.issubset(columns), (
            f"Missing columns in messages: {expected_columns - columns}"
        )


class TestDatabaseConnectivity:
    """Test database connectivity and health checks."""

    def test_healthz_works_with_database(self, db_client):
        """Health check should work with database configured."""
        response = db_client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_request_id_header_present(self, db_client):
        """X-Request-ID header should be present."""
        response = db_client.get("/healthz")
        assert "X-Request-ID" in response.headers

    def test_database_select_works(self, migrated_db):
        """Simple SELECT 1 should work after migrations."""
        from app.db import get_engine

        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1


class TestDatabaseSession:
    """Test database session management."""

    def test_get_db_yields_session(self, migrated_db):
        """get_db should yield a valid session."""
        from app.db import get_db

        # Use the generator properly
        gen = get_db()
        session = next(gen)

        # Session should be able to execute queries
        result = session.execute(text("SELECT 1"))
        assert result.scalar() == 1

        # Close the session by finishing the generator
        session.close()
