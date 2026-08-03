import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_lifespan_eagerly_resolves_settings_at_startup(monkeypatch):
    calls = []

    def spy_get_settings():
        calls.append(True)
        raise KeyError("DATABASE_URL")  # short-circuits before build_jwks_provider runs

    monkeypatch.setattr("app.main.get_settings", spy_get_settings)

    with pytest.raises(KeyError):
        with TestClient(app):
            pass

    assert calls, "lifespan should call get_settings() at startup, before serving any request"


def test_lifespan_respects_dependency_overrides(test_settings):
    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        with TestClient(app):
            pass  # must not raise — test_settings carries a valid static JWKS
    finally:
        app.dependency_overrides.clear()
