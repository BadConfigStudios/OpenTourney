import jwt


class FakeUnreachableJWKSProvider:
    """Simulates a JWKS source (e.g. the IdP) that cannot be reached over the network."""

    def get_signing_key(self, token: str):
        raise jwt.PyJWKClientConnectionError("simulated JWKS fetch failure")
