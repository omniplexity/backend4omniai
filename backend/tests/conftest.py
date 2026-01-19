import pytest
import gc
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker
from alembic.config import Config
from alembic import command
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.session import get_db
from backend.app.config.settings import settings


@pytest.fixture(scope="session")
def project_root():
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def tmp_db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def engine(tmp_db_path):
    db_url = f"sqlite:///{tmp_db_path}"
    engine = create_engine(
        db_url,
        poolclass=NullPool,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    # Force journal mode DELETE to avoid WAL locking on Windows
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=DELETE;"))
        conn.execute(text("PRAGMA synchronous=NORMAL;"))
    yield engine
    engine.dispose()


def apply_migrations(engine, db_url, project_root):
    cfg = Config(str(project_root / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "backend" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")


@pytest.fixture
def db_session(engine, tmp_db_path, project_root):
    db_url = f"sqlite:///{tmp_db_path}"
    apply_migrations(engine, db_url, project_root)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    # Force garbage collection to release locks
    gc.collect()


@pytest.fixture
def client(engine, db_session):
    # Store original settings
    original_database_url = settings.database_url
    original_cookie_secure = settings.cookie_secure
    original_invite_only = settings.invite_only
    original_admin_bootstrap_token = settings.admin_bootstrap_token

    # Override settings for testing
    settings.database_url = str(engine.url)
    settings.cookie_secure = False
    settings.invite_only = True
    settings.admin_bootstrap_token = "test-bootstrap-token"

    # Reset engine and session for new DB URL
    from backend.app.db.engine import reset_engine_for_tests
    from backend.app.db.session import reset_sessionmaker_for_tests
    reset_engine_for_tests()
    reset_sessionmaker_for_tests()

    # Rebuild provider registry with new settings
    from backend.app.providers.registry import registry
    registry._providers.clear()
    registry.build_registry()

    def override_get_db():
        yield db_session

    try:
        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        # Restore original settings
        settings.database_url = original_database_url
        settings.cookie_secure = original_cookie_secure
        settings.invite_only = original_invite_only
        settings.admin_bootstrap_token = original_admin_bootstrap_token