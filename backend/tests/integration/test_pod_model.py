import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Event, Pod


def test_pod_persists_linked_to_event(db_session):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()

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
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()

    db_session.add(Pod(event_id=event.id, format_slug="swiss", game_slug="generic"))
    db_session.commit()

    # A second Pod row for the same event_id, inserted directly at the model layer
    # (bypassing the router's app-level pre-check), must still be rejected by the DB —
    # this is what actually closes the race window between two concurrent POST /pods
    # requests for the same event.
    db_session.add(Pod(event_id=event.id, format_slug="swiss", game_slug="pokemon-tcg"))
    with pytest.raises(IntegrityError):
        db_session.commit()
