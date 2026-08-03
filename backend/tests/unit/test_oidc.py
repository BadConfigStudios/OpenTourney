import time

import jwt
import pytest

from app.auth.jwks import StaticJWKSProvider
from app.auth.oidc import AuthError, AuthServiceUnavailableError, decode_token
from app.config import Settings
from tests.support.jwt_helpers import generate_test_keypair, mint_token


def _settings(jwks_json: str) -> Settings:
    return Settings(
        database_url="unused",
        oidc_issuer="https://issuer.example.com",
        oidc_audience="opentourney-test",
        oidc_jwks_url=None,
        oidc_jwks_static=jwks_json,
    )


def test_decode_token_returns_claims_for_a_valid_token():
    private_key, jwks_json = generate_test_keypair(kid="k1")
    token = mint_token(
        private_key,
        kid="k1",
        issuer="https://issuer.example.com",
        audience="opentourney-test",
        player_uuid="11111111-1111-1111-1111-111111111111",
        source_system="club-checkin",
    )
    settings = _settings(jwks_json)

    claims = decode_token(token, settings, StaticJWKSProvider(jwks_json))

    assert claims["sub"] == "11111111-1111-1111-1111-111111111111"


def test_decode_token_rejects_wrong_audience():
    private_key, jwks_json = generate_test_keypair(kid="k1")
    token = mint_token(
        private_key,
        kid="k1",
        issuer="https://issuer.example.com",
        audience="someone-else",
        player_uuid="11111111-1111-1111-1111-111111111111",
        source_system="club-checkin",
    )
    settings = _settings(jwks_json)

    with pytest.raises(AuthError):
        decode_token(token, settings, StaticJWKSProvider(jwks_json))


def test_decode_token_rejects_tampered_signature():
    private_key, jwks_json = generate_test_keypair(kid="k1")
    token = mint_token(
        private_key,
        kid="k1",
        issuer="https://issuer.example.com",
        audience="opentourney-test",
        player_uuid="11111111-1111-1111-1111-111111111111",
        source_system="club-checkin",
    )
    settings = _settings(jwks_json)

    with pytest.raises(AuthError):
        decode_token(token + "x", settings, StaticJWKSProvider(jwks_json))


@pytest.mark.parametrize("missing_claim", ["exp", "iat", "iss", "aud", "sub"])
def test_decode_token_rejects_token_missing_a_required_claim(missing_claim):
    private_key, jwks_json = generate_test_keypair(kid="k1")
    now = int(time.time())
    claims = {
        "iss": "https://issuer.example.com",
        "aud": "opentourney-test",
        "sub": "11111111-1111-1111-1111-111111111111",
        "source_system": "club-checkin",
        "iat": now,
        "exp": now + 3600,
    }
    del claims[missing_claim]
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "k1"})
    settings = _settings(jwks_json)

    with pytest.raises(AuthError):
        decode_token(token, settings, StaticJWKSProvider(jwks_json))


class _FakeUnreachableJWKSProvider:
    """Simulates a JWKS source that cannot be reached over the network."""

    def get_signing_key(self, token: str):
        raise jwt.PyJWKClientConnectionError("simulated JWKS fetch failure")


def test_decode_token_reraises_jwks_connection_failure_as_service_unavailable():
    settings = _settings(jwks_json='{"keys": []}')

    with pytest.raises(AuthServiceUnavailableError):
        decode_token("irrelevant-token", settings, _FakeUnreachableJWKSProvider())
