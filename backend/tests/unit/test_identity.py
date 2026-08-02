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
