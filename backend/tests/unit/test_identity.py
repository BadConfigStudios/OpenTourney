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
