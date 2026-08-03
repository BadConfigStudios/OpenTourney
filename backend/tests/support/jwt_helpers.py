import json
import time
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from jwt.algorithms import RSAAlgorithm


def generate_test_keypair(kid: str = "test-key") -> tuple[RSAPrivateKey, str]:
    """Generate a real RSA keypair and its public JWK set (as JSON) for signing test tokens."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk["kid"] = kid
    public_jwk["use"] = "sig"
    public_jwk["alg"] = "RS256"
    jwks_json = json.dumps({"keys": [public_jwk]})
    return private_key, jwks_json


def mint_token(
    private_key,
    *,
    kid: str,
    issuer: str,
    audience: str,
    player_uuid: uuid.UUID | str,
    source_system: str,
    roles: list[str] | None = None,
    expires_in: int = 3600,
) -> str:
    """Sign a JWT with the given private key, shaped like OpenTourney's expected OIDC assertion."""
    now = int(time.time())
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": str(player_uuid),
        "source_system": source_system,
        "roles": roles or [],
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})
