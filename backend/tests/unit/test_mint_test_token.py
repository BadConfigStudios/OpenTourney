import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import jwt

from mint_test_token import mint_token
from tests.support.jwt_helpers import generate_test_keypair


def test_mint_token_produces_a_verifiable_token():
    private_key, jwks_json = generate_test_keypair(kid="staging-key")

    token = mint_token(
        private_key,
        kid="staging-key",
        issuer="https://staging-issuer.example.com",
        audience="opentourney-staging",
        player_uuid="22222222-2222-2222-2222-222222222222",
        source_system="manual-verification",
        roles=["organizer"],
    )

    signing_key = jwt.PyJWKSet.from_json(jwks_json).keys[0]
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience="opentourney-staging",
        issuer="https://staging-issuer.example.com",
    )
    assert claims["roles"] == ["organizer"]
