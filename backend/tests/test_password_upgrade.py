from pathlib import Path

import bcrypt
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.config import get_settings
from backend.db import Base, dispose_engine
from backend.db.database import get_engine
from backend.db.models import User
from backend.main import create_app


def _setup_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "pwd_upgrade.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("DATABASE_URL_POSTGRES", "")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_ENABLED", "false")
    get_settings.cache_clear()
    dispose_engine()
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    return engine


def _get_session(engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def test_login_upgrades_bcrypt_to_argon2id(monkeypatch, tmp_path):
    engine = _setup_db(tmp_path, monkeypatch)
    db = _get_session(engine)
    try:
        bcrypt_hash = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode("utf-8")
        user = User(
            email="u@example.com",
            username="u1",
            hashed_password=bcrypt_hash,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    finally:
        db.close()

    app = create_app()
    with TestClient(app) as client:
        res = client.post("/api/auth/login", json={"username": "u1", "password": "password123"})
        assert res.status_code == 200

    db = _get_session(engine)
    try:
        refreshed = db.query(User).filter(User.id == user_id).first()
        assert refreshed is not None
        assert refreshed.hashed_password.startswith("$argon2")
    finally:
        db.close()
        dispose_engine()

