import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Organization, OrganizationMember, OrgRoleName


def test_organization_persists(db_session):
    org = Organization(name="Dragon's Den")
    db_session.add(org)
    db_session.commit()

    assert org.id is not None
    assert org.name == "Dragon's Den"


def test_organization_member_persists_with_role(db_session):
    org = Organization(name="Dragon's Den")
    db_session.add(org)
    db_session.flush()

    member = OrganizationMember(
        organization_id=org.id,
        player_uuid=uuid.uuid4(),
        source_system="club-checkin",
        role=OrgRoleName.OWNER,
    )
    db_session.add(member)
    db_session.commit()

    assert member.id is not None
    assert member.role == OrgRoleName.OWNER


def test_organization_member_rejects_duplicate_identity_in_same_org(db_session):
    org = Organization(name="Dragon's Den")
    db_session.add(org)
    db_session.flush()
    player_uuid = uuid.uuid4()

    db_session.add(
        OrganizationMember(
            organization_id=org.id,
            player_uuid=player_uuid,
            source_system="club-checkin",
            role=OrgRoleName.OWNER,
        )
    )
    db_session.commit()

    db_session.add(
        OrganizationMember(
            organization_id=org.id,
            player_uuid=player_uuid,
            source_system="club-checkin",
            role=OrgRoleName.ORGANIZER,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_organization_member_requires_existing_organization(db_session):
    member = OrganizationMember(
        organization_id=uuid.uuid4(),
        player_uuid=uuid.uuid4(),
        source_system="club-checkin",
        role=OrgRoleName.OWNER,
    )
    db_session.add(member)

    with pytest.raises(IntegrityError):
        db_session.commit()
