import os
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_FORBIDDEN_PATTERN = re.compile(r"PORTAL_API_KEY|X-Api-Key", re.IGNORECASE)


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


def test_settings_raises_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    # D9 (REQ-013 §9): PORTAL_HUB_API_KEY / PORTAL_HUB_API_SECRET have NO
    # default, so a deploy missing either fails at Settings() construction
    # (process start) rather than at the first request to the Portal gate.
    monkeypatch.delenv("PORTAL_HUB_API_KEY", raising=False)
    monkeypatch.delenv("PORTAL_HUB_API_SECRET", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_loads_portal_hub_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORTAL_HUB_API_KEY", "test-key")
    monkeypatch.setenv("PORTAL_HUB_API_SECRET", "test-secret")

    settings = Settings()

    assert settings.PORTAL_HUB_API_KEY == "test-key"
    assert settings.PORTAL_HUB_API_SECRET == "test-secret"


def test_portal_api_key_setting_no_longer_exists() -> None:
    # REQ-013 §10 row 2: retired, not defaulted to None — a stale code
    # reference must fail loudly with AttributeError at access time.
    assert not hasattr(Settings(), "PORTAL_API_KEY")


def test_no_portal_api_key_or_x_api_key_references_in_backend_source() -> None:
    """Grep-style check (task 4.7, design §10 row 2). Scoped to `app/` —
    the only tree this container mounts (`docker-compose.yml`'s `backend`
    service binds `./src/backend/app`, `tests`, and `alembic` only, never the
    repo root). The repo-root sweep (`.env.example`, compose files, and the
    rest of `src/`) is task 7.6's final gate, run from the host shell where
    the whole repository is visible — this test cannot reach those paths
    from inside the container and must not silently pass by skipping them.
    """
    app_root = Path(__file__).resolve().parents[1] / "app"
    offending: list[str] = []
    for path in app_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _FORBIDDEN_PATTERN.search(text):
            offending.append(str(path))

    assert offending == [], f"PORTAL_API_KEY/X-Api-Key reference(s) found: {offending}"
