import uuid

import pytest

from app.auth.identity import identity_from_claims
from app.auth.oidc import AuthError


def test_identity_from_claims_extracts_player_and_source_system():
    player_uuid = uuid.uuid4()

    identity = identity_from_claims(
        {"sub": str(player_uuid), "source_system": "club-checkin", "roles": []}
    )

    assert identity.player_uuid == player_uuid
    assert identity.source_system == "club-checkin"
    assert identity.has_organizer_claim is False


def test_identity_from_claims_detects_organizer_role():
    identity = identity_from_claims(
        {
            "sub": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "roles": ["organizer"],
        }
    )

    assert identity.has_organizer_claim is True


def test_identity_from_claims_raises_for_missing_sub():
    with pytest.raises(AuthError):
        identity_from_claims({"source_system": "club-checkin"})


def test_identity_from_claims_raises_for_missing_source_system():
    with pytest.raises(AuthError):
        identity_from_claims({"sub": str(uuid.uuid4())})


def test_identity_from_claims_raises_when_roles_is_a_string_instead_of_a_list():
    # A string "roles" claim must not be substring-matched against "organizer" —
    # e.g. "event-organizer-lite" would otherwise incorrectly grant the claim.
    with pytest.raises(AuthError, match="roles"):
        identity_from_claims(
            {
                "sub": str(uuid.uuid4()),
                "source_system": "club-checkin",
                "roles": "event-organizer-lite",
            }
        )


def test_identity_from_claims_treats_a_null_roles_claim_as_no_roles():
    # A literal JSON null for "roles" must not raise an unhandled TypeError from
    # `"organizer" in None` — it's treated the same as a missing roles claim.
    identity = identity_from_claims(
        {"sub": str(uuid.uuid4()), "source_system": "club-checkin", "roles": None}
    )

    assert identity.has_organizer_claim is False


def test_identity_from_claims_raises_when_source_system_is_not_a_string():
    with pytest.raises(AuthError, match="source_system"):
        identity_from_claims(
            {"sub": str(uuid.uuid4()), "source_system": 12345, "roles": []}
        )


def test_identity_from_claims_derives_a_uuid_for_a_non_uuid_sub():
    # Real external identity providers (Zitadel's numeric snowflake sub, and
    # Google's opaque sub per FR30) are not UUID-formatted, unlike MVP1's
    # static/local-dev tokens. A non-UUID sub must no longer raise -- it's
    # deterministically mapped to a UUID instead.
    identity = identity_from_claims(
        {"sub": "386717021213032479", "source_system": "zitadel", "roles": []}
    )

    assert isinstance(identity.player_uuid, uuid.UUID)


def test_identity_from_claims_derives_the_same_uuid_for_the_same_sub_every_time():
    # Determinism is required: a user's grant history (PodRole, etc.) is keyed
    # on player_uuid, so the same real-world identity must always map to the
    # same UUID across every login, not a fresh random one per call.
    claims = {"sub": "386717021213032479", "source_system": "zitadel", "roles": []}

    first = identity_from_claims(claims)
    second = identity_from_claims(claims)

    assert first.player_uuid == second.player_uuid


def test_identity_from_claims_derives_different_uuids_for_the_same_sub_under_different_source_systems():
    # The derivation is namespaced by source_system so a numerically
    # coincidental sub collision across two different identity providers
    # can't collide into the same player_uuid.
    zitadel_identity = identity_from_claims(
        {"sub": "12345", "source_system": "zitadel", "roles": []}
    )
    other_identity = identity_from_claims(
        {"sub": "12345", "source_system": "google", "roles": []}
    )

    assert zitadel_identity.player_uuid != other_identity.player_uuid


def test_identity_from_claims_still_uses_a_uuid_sub_directly_unmodified():
    # A UUID-formatted sub (MVP1's static/local-dev tokens, still in use in
    # this test file's other cases) must keep round-tripping exactly as-is,
    # not get re-derived through the UUID5 fallback.
    player_uuid = uuid.uuid4()

    identity = identity_from_claims(
        {"sub": str(player_uuid), "source_system": "club-checkin", "roles": []}
    )

    assert identity.player_uuid == player_uuid
