import json
import uuid

import jwt

from tests.support.jwt_helpers import generate_test_keypair, mint_token


def test_generate_test_keypair_returns_usable_jwk_set():
    _, jwks_json = generate_test_keypair(kid="k1")

    jwk_set = json.loads(jwks_json)

    assert jwk_set["keys"][0]["kid"] == "k1"
    assert jwk_set["keys"][0]["kty"] == "RSA"


def test_mint_token_is_decodable_with_the_matching_public_key():
    private_key, jwks_json = generate_test_keypair(kid="k1")
    player_uuid = uuid.uuid4()

    token = mint_token(
        private_key,
        kid="k1",
        issuer="https://issuer.example.com",
        audience="opentourney-test",
        player_uuid=player_uuid,
        source_system="club-checkin",
        roles=["organizer"],
    )

    signing_key = jwt.PyJWKSet.from_json(jwks_json).keys[0]
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience="opentourney-test",
        issuer="https://issuer.example.com",
    )

    assert claims["sub"] == str(player_uuid)
    assert claims["source_system"] == "club-checkin"
    assert claims["roles"] == ["organizer"]
