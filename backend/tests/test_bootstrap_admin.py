from pathlib import Path

from sqlalchemy.orm import sessionmaker

from backend.auth.bootstrap import ensure_bootstrap_admin
from backend.config import get_settings
from backend.db import Base, dispose_engine
from backend.db.database import get_engine
from backend.db.models import User


def _setup_db(tmp_path: Path, monkeypatch, **env):
    db_path = tmp_path / "bootstrap_admin.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("DATABASE_URL_POSTGRES", "")
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    dispose_engine()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    return engine


def _get_session(engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def test_bootstrap_creates_admin(monkeypatch, tmp_path):
    engine = _setup_db(
        tmp_path,
        monkeypatch,
        BOOTSTRAP_ADMIN_ENABLED="true",
        BOOTSTRAP_ADMIN_USERNAME="admin",
        BOOTSTRAP_ADMIN_EMAIL="admin@example.com",
        BOOTSTRAP_ADMIN_PASSWORD="password123",
    )

    settings = get_settings()
    ensure_bootstrap_admin(settings)

    db = _get_session(engine)
    try:
        admin = db.query(User).filter(User.is_admin == True).first()
        assert admin is not None
        assert admin.username == "admin"
        assert admin.email == "admin@example.com"
    finally:
        db.close()
        dispose_engine()


def test_bootstrap_skips_if_admin_exists(monkeypatch, tmp_path):
    engine = _setup_db(
        tmp_path,
        monkeypatch,
        BOOTSTRAP_ADMIN_ENABLED="true",
        BOOTSTRAP_ADMIN_USERNAME="admin2",
        BOOTSTRAP_ADMIN_EMAIL="admin2@example.com",
        BOOTSTRAP_ADMIN_PASSWORD="password123",
    )

    db = _get_session(engine)
    try:
        db.add(
            User(
                email="existing@example.com",
                username="existing",
                hashed_password="hashed",
                is_admin=True,
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    settings = get_settings()
    ensure_bootstrap_admin(settings)

    db = _get_session(engine)
    try:
        admins = db.query(User).filter(User.is_admin == True).all()
        assert len(admins) == 1
        assert admins[0].username == "existing"
    finally:
        db.close()
        dispose_engine()


def test_bootstrap_skips_if_missing_env(monkeypatch, tmp_path):
    engine = _setup_db(
        tmp_path,
        monkeypatch,
        BOOTSTRAP_ADMIN_ENABLED="true",
        BOOTSTRAP_ADMIN_USERNAME="admin",
        BOOTSTRAP_ADMIN_EMAIL="admin@example.com",
        BOOTSTRAP_ADMIN_PASSWORD="",
    )

    settings = get_settings()
    ensure_bootstrap_admin(settings)

    db = _get_session(engine)
    try:
        admin = db.query(User).filter(User.is_admin == True).first()
        assert admin is None
    finally:
        db.close()
        dispose_engine()
