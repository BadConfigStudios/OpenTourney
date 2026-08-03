import os
from dataclasses import dataclass
from functools import lru_cache


def normalize_database_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+psycopg://", 1)
    return raw_url


@dataclass(frozen=True)
class Settings:
    database_url: str
    oidc_issuer: str
    oidc_audience: str
    oidc_jwks_url: str | None
    oidc_jwks_static: str | None


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=normalize_database_url(os.environ["DATABASE_URL"]),
        oidc_issuer=os.environ["OIDC_ISSUER"],
        oidc_audience=os.environ["OIDC_AUDIENCE"],
        oidc_jwks_url=os.environ.get("OIDC_JWKS_URL"),
        oidc_jwks_static=os.environ.get("OIDC_JWKS_STATIC"),
    )
