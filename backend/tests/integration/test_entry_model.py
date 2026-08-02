import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Entry, Event, Pod


def _make_pod(db_session) -> Pod:
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    return pod


def test_entry_persists_with_metadata(db_session):
    pod = _make_pod(db_session)
    player_uuid = uuid.uuid4()

    entry = Entry(
        pod_id=pod.id,
        player_uuid=player_uuid,
        source_system="club-checkin",
        metadata_={"display_name": "Ash"},
    )
    db_session.add(entry)
    db_session.commit()

    assert entry.id is not None
    assert entry.metadata_ == {"display_name": "Ash"}


def test_entry_rejects_duplicate_player_in_same_pod(db_session):
    pod = _make_pod(db_session)
    player_uuid = uuid.uuid4()
    db_session.add(
        Entry(pod_id=pod.id, player_uuid=player_uuid, source_system="club-checkin", metadata_={})
    )
    db_session.commit()

    db_session.add(
        Entry(pod_id=pod.id, player_uuid=player_uuid, source_system="club-checkin", metadata_={})
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
