import uuid
from dataclasses import dataclass

from app.auth.oidc import AuthError


@dataclass(frozen=True)
class Identity:
    player_uuid: uuid.UUID
    source_system: str
    has_organizer_claim: bool


def identity_from_claims(claims: dict) -> Identity:
    try:
        player_uuid = uuid.UUID(str(claims["sub"]))
        source_system = claims["source_system"]
    except (KeyError, ValueError) as exc:
        raise AuthError(
            "token is missing required identity claims (sub, source_system)"
        ) from exc

    if not isinstance(source_system, str):
        raise AuthError("token 'source_system' claim must be a string")

    roles = claims.get("roles") or []
    if not isinstance(roles, list):
        raise AuthError("token 'roles' claim must be a list")

    return Identity(
        player_uuid=player_uuid,
        source_system=source_system,
        has_organizer_claim="organizer" in roles,
    )
