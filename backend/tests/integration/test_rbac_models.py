import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError

from app.models import Event, Pod
from app.models.rbac import EventOrganizer, PodRole, PodRoleName


def _make_event(db_session) -> Event:
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    return event


def _make_pod(db_session, event) -> Pod:
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    return pod


def test_event_organizer_persists(db_session):
    event = _make_event(db_session)
    player_uuid = uuid.uuid4()

    db_session.add(
        EventOrganizer(event_id=event.id, player_uuid=player_uuid, source_system="club-checkin")
    )
    db_session.commit()

    row = db_session.query(EventOrganizer).one()
    assert row.event_id == event.id
    assert row.player_uuid == player_uuid


def test_event_organizer_rejects_duplicate_identity_per_event(db_session):
    event = _make_event(db_session)
    player_uuid = uuid.uuid4()
    db_session.add(
        EventOrganizer(event_id=event.id, player_uuid=player_uuid, source_system="club-checkin")
    )
    db_session.commit()

    db_session.add(
        EventOrganizer(event_id=event.id, player_uuid=player_uuid, source_system="club-checkin")
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_event_organizer_requires_existing_event(db_session):
    db_session.add(
        EventOrganizer(event_id=uuid.uuid4(), player_uuid=uuid.uuid4(), source_system="x")
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_pod_role_persists_with_role_enum(db_session):
    event = _make_event(db_session)
    pod = _make_pod(db_session, event)
    player_uuid = uuid.uuid4()

    db_session.add(
        PodRole(
            pod_id=pod.id,
            player_uuid=player_uuid,
            source_system="club-checkin",
            role=PodRoleName.SCOREKEEPER,
        )
    )
    db_session.commit()

    row = db_session.query(PodRole).one()
    assert row.role == PodRoleName.SCOREKEEPER


def test_pod_role_rejects_duplicate_identity_per_pod(db_session):
    event = _make_event(db_session)
    pod = _make_pod(db_session, event)
    player_uuid = uuid.uuid4()
    db_session.add(
        PodRole(
            pod_id=pod.id,
            player_uuid=player_uuid,
            source_system="club-checkin",
            role=PodRoleName.USER,
        )
    )
    db_session.commit()

    db_session.add(
        PodRole(
            pod_id=pod.id,
            player_uuid=player_uuid,
            source_system="club-checkin",
            role=PodRoleName.SCOREKEEPER,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_pod_role_requires_existing_pod(db_session):
    db_session.add(
        PodRole(
            pod_id=uuid.uuid4(),
            player_uuid=uuid.uuid4(),
            source_system="club-checkin",
            role=PodRoleName.USER,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_pod_role_rejects_invalid_role_value(db_session):
    event = _make_event(db_session)
    pod = _make_pod(db_session, event)

    with pytest.raises(DataError):
        db_session.execute(
            text(
                "INSERT INTO pod_roles (id, pod_id, player_uuid, source_system, role) "
                "VALUES (gen_random_uuid(), :pod_id, gen_random_uuid(), 'club-checkin', 'not-a-real-role')"
            ),
            {"pod_id": pod.id},
        )
