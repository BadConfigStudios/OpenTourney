import uuid
from dataclasses import dataclass

from app.auth.oidc import AuthError

# Fixed namespace for deriving a player_uuid from a non-UUID `sub` claim (real
# external identity providers -- Zitadel's numeric snowflake sub, and Google's
# opaque sub per FR30 -- don't issue UUID-formatted subs, unlike MVP1's
# static/local-dev tokens). Must never change once any real identity has been
# derived from it: every existing derived player_uuid is a function of this
# constant, so rotating it would silently orphan every prior grant
# (PodRole/OrganizationMember, etc.) from the identity that earned it.
_IDENTITY_NAMESPACE = uuid.UUID("6adf2aac-85bf-4e2e-bbe4-eed68f59dc43")


@dataclass(frozen=True)
class Identity:
    player_uuid: uuid.UUID
    source_system: str
    has_organizer_claim: bool


def identity_from_claims(claims: dict) -> Identity:
    try:
        sub = claims["sub"]
        source_system = claims["source_system"]
    except KeyError as exc:
        raise AuthError(
            "token is missing required identity claims (sub, source_system)"
        ) from exc

    if not isinstance(source_system, str):
        raise AuthError("token 'source_system' claim must be a string")

    # A falsy sub (empty string, null, 0) is not a real identity -- reject it
    # explicitly rather than letting it fall into the uuid5 fallback below.
    # Before the uuid5 fallback existed, uuid.UUID("") already raised
    # ValueError and this was rejected; without this guard it would now
    # silently derive a real, usable player_uuid from a degenerate value
    # (e.g. every sub="" token would collide onto the same identity).
    if not sub:
        raise AuthError("token 'sub' claim must not be empty")

    try:
        player_uuid = uuid.UUID(str(sub))
    except ValueError:
        # Not UUID-formatted -- derive a stable UUID instead of rejecting it.
        # Deterministic (same source_system+sub always produces the same
        # output) so a user's grant history stays keyed to the same
        # player_uuid across every login. Namespaced by source_system so a
        # numerically coincidental sub collision across two different
        # identity providers can't collide into the same player_uuid --
        # source_system's length is prefixed so the two fields can't be
        # ambiguously re-split if either ever contains a ":" (source_system
        # is currently a fixed IdP-stamped literal, not user input, but
        # nothing enforces that at this layer).
        player_uuid = uuid.uuid5(
            _IDENTITY_NAMESPACE, f"{len(source_system)}:{source_system}:{sub}"
        )

    roles = claims.get("roles") or []
    if not isinstance(roles, list):
        raise AuthError("token 'roles' claim must be a list")

    return Identity(
        player_uuid=player_uuid,
        source_system=source_system,
        has_organizer_claim="organizer" in roles,
    )
