import uuid
from datetime import date

import pytest
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.models import Event, Organization, Pod


def _make_event(db_session) -> Event:
    org = Organization(name="Test Org")
    db_session.add(org)
    db_session.flush()
    event = Event(date=date(2026, 9, 1), name="Test Event", organization_id=org.id)
    db_session.add(event)
    db_session.flush()
    return event


def test_pod_persists_linked_to_event(db_session):
    event = _make_event(db_session)

    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.commit()

    assert pod.id is not None
    assert pod.event_id == event.id


def test_pod_requires_existing_event(db_session):
    pod = Pod(event_id=uuid.uuid4(), format_slug="swiss", game_slug="generic")
    db_session.add(pod)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_pod_event_id_is_unique_at_db_level(db_session):
    event = _make_event(db_session)

    db_session.add(Pod(event_id=event.id, format_slug="swiss", game_slug="generic"))
    db_session.commit()

    # A second Pod row for the same event_id, inserted directly at the model layer
    # (bypassing the router's app-level pre-check), must still be rejected by the DB —
    # this is what actually closes the race window between two concurrent POST /pods
    # requests for the same event.
    db_session.add(Pod(event_id=event.id, format_slug="swiss", game_slug="pokemon-tcg"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_pod_completed_at_defaults_to_none(db_session):
    event = _make_event(db_session)

    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.commit()

    assert pod.completed_at is None


def test_pod_completed_at_can_be_set(db_session):
    event = _make_event(db_session)
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.commit()

    pod.completed_at = func.now()
    db_session.commit()
    db_session.refresh(pod)

    assert pod.completed_at is not None
