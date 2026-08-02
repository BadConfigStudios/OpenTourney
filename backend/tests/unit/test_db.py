from app.config import Settings
from app.db import get_engine


def test_get_engine_enables_pool_pre_ping(monkeypatch):
    # Percona PG failovers/idle-reaping can leave stale pooled connections; pool_pre_ping
    # makes SQLAlchemy test a connection before handing it out instead of surfacing a
    # mid-request OperationalError.
    captured_kwargs = {}

    def fake_create_engine(url, **kwargs):
        captured_kwargs["url"] = url
        captured_kwargs.update(kwargs)
        return object()

    monkeypatch.setattr("app.db.create_engine", fake_create_engine)
    monkeypatch.setattr(
        "app.db.get_settings",
        lambda: Settings(
            database_url="postgresql+psycopg://unused/db",
            oidc_issuer="https://issuer.example.com",
            oidc_audience="aud",
            oidc_jwks_url=None,
            oidc_jwks_static=None,
        ),
    )
    get_engine.cache_clear()

    try:
        get_engine()
    finally:
        get_engine.cache_clear()

    assert captured_kwargs["pool_pre_ping"] is True
