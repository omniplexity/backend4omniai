import pytest

from backend.config import get_settings


def test_cookie_samesite_normalizes(monkeypatch):
    monkeypatch.setenv("COOKIE_SAMESITE", "None")
    get_settings.cache_clear()
    s = get_settings()
    assert s.cookie_samesite == "none"


def test_cookie_samesite_rejects_invalid(monkeypatch):
    monkeypatch.setenv("COOKIE_SAMESITE", "invalid")
    get_settings.cache_clear()
    with pytest.raises(Exception):
        get_settings()


def test_cookie_samesite_none_requires_secure(monkeypatch):
    monkeypatch.setenv("COOKIE_SAMESITE", "none")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    get_settings.cache_clear()
    with pytest.raises(Exception):
        get_settings()


def test_production_cors_requires_https(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,https://omniplexity.github.io")
    get_settings.cache_clear()
    with pytest.raises(Exception):
        get_settings()
