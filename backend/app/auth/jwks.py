from typing import Protocol

import jwt
from jwt import PyJWK, PyJWKClient, PyJWKSet

from app.config import Settings


class JWKSProvider(Protocol):
    def get_signing_key(self, token: str) -> PyJWK: ...


class RemoteJWKSProvider:
    def __init__(self, jwks_url: str) -> None:
        self._client = PyJWKClient(jwks_url)

    def get_signing_key(self, token: str) -> PyJWK:
        return self._client.get_signing_key_from_jwt(token)


class StaticJWKSProvider:
    def __init__(self, jwks_json: str) -> None:
        self._jwk_set = PyJWKSet.from_json(jwks_json)

    def get_signing_key(self, token: str) -> PyJWK:
        kid = jwt.get_unverified_header(token).get("kid")
        for key in self._jwk_set.keys:
            if key.key_id == kid:
                return key
        raise jwt.InvalidTokenError(f"no JWKS key found for kid={kid!r}")


def build_jwks_provider(settings: Settings) -> JWKSProvider:
    if settings.oidc_jwks_static:
        return StaticJWKSProvider(settings.oidc_jwks_static)
    if settings.oidc_jwks_url:
        return RemoteJWKSProvider(settings.oidc_jwks_url)
    raise RuntimeError("neither OIDC_JWKS_STATIC nor OIDC_JWKS_URL is configured")
