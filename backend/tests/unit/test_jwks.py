import pytest

from app.auth.jwks import StaticJWKSProvider, build_jwks_provider
from app.config import Settings
from tests.support.jwt_helpers import generate_test_keypair, mint_token


def test_static_provider_returns_matching_key_by_kid():
    private_key, jwks_json = generate_test_keypair(kid="k1")
    token = mint_token(
        private_key,
        kid="k1",
        issuer="https://issuer.example.com",
        audience="aud",
        player_uuid="00000000-0000-0000-0000-000000000000",
        source_system="club-checkin",
    )

    provider = StaticJWKSProvider(jwks_json)
    signing_key = provider.get_signing_key(token)

    assert signing_key.key_id == "k1"


def test_static_provider_raises_for_unknown_kid():
    _, jwks_json = generate_test_keypair(kid="k1")
    other_private_key, _ = generate_test_keypair(kid="k2")
    token = mint_token(
        other_private_key,
        kid="k2",
        issuer="https://issuer.example.com",
        audience="aud",
        player_uuid="00000000-0000-0000-0000-000000000000",
        source_system="club-checkin",
    )

    provider = StaticJWKSProvider(jwks_json)

    with pytest.raises(Exception, match="no JWKS key found"):
        provider.get_signing_key(token)


def test_build_jwks_provider_prefers_static_over_remote():
    _, jwks_json = generate_test_keypair()
    settings = Settings(
        database_url="unused",
        oidc_issuer="https://issuer.example.com",
        oidc_audience="aud",
        oidc_jwks_url="https://issuer.example.com/.well-known/jwks.json",
        oidc_jwks_static=jwks_json,
    )

    provider = build_jwks_provider(settings)

    assert provider.__class__.__name__ == "StaticJWKSProvider"


def test_build_jwks_provider_raises_when_nothing_configured():
    settings = Settings(
        database_url="unused",
        oidc_issuer="https://issuer.example.com",
        oidc_audience="aud",
        oidc_jwks_url=None,
        oidc_jwks_static=None,
    )

    with pytest.raises(RuntimeError, match="neither OIDC_JWKS_STATIC nor OIDC_JWKS_URL"):
        build_jwks_provider(settings)
