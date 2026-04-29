import os

import pytest

from app.core.config import Settings


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_pass")
    monkeypatch.setenv("POSTGRES_DB", "test_db")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")

    settings = Settings()

    assert settings.POSTGRES_USER == "test_user"
    assert settings.POSTGRES_PASSWORD == "test_pass"
    assert settings.POSTGRES_DB == "test_db"
    assert settings.SECRET_KEY == "test-secret"
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 30
    assert "test_user" in settings.DATABASE_URL or settings.DATABASE_URL.startswith("postgresql")


def test_settings_has_required_attributes() -> None:
    settings = Settings()
    assert hasattr(settings, "DATABASE_URL")
    assert hasattr(settings, "SECRET_KEY")
    assert hasattr(settings, "ALGORITHM")
    assert hasattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES")
    assert settings.ALGORITHM == "HS256"
