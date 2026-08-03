import pytest

from app.config import get_settings, normalize_database_url


def test_normalizes_bare_postgresql_scheme():
    assert (
        normalize_database_url("postgresql://u:p@host/db")
        == "postgresql+psycopg://u:p@host/db"
    )


def test_normalizes_bare_postgres_scheme():
    assert (
        normalize_database_url("postgres://u:p@host/db")
        == "postgresql+psycopg://u:p@host/db"
    )


def test_leaves_already_qualified_scheme_untouched():
    assert (
        normalize_database_url("postgresql+psycopg://u:p@host/db")
        == "postgresql+psycopg://u:p@host/db"
    )


def test_get_settings_reads_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@host/db")
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example.com")
    monkeypatch.setenv("OIDC_AUDIENCE", "aud")
    monkeypatch.delenv("OIDC_JWKS_URL", raising=False)
    monkeypatch.delenv("OIDC_JWKS_STATIC", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.database_url == "postgresql+psycopg://u:p@host/db"
    assert settings.oidc_issuer == "https://issuer.example.com"
    assert settings.oidc_audience == "aud"
    assert settings.oidc_jwks_url is None
    assert settings.oidc_jwks_static is None

    get_settings.cache_clear()


def test_get_settings_raises_key_error_when_a_required_var_is_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example.com")
    monkeypatch.setenv("OIDC_AUDIENCE", "aud")
    get_settings.cache_clear()

    with pytest.raises(KeyError):
        get_settings()

    get_settings.cache_clear()
