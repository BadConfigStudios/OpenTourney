import jwt

from app.auth.jwks import JWKSProvider
from app.config import Settings


class AuthError(Exception):
    """Raised when an identity assertion fails to validate."""


def decode_token(token: str, settings: Settings, jwks_provider: JWKSProvider) -> dict:
    try:
        signing_key = jwks_provider.get_signing_key(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
        )
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc
