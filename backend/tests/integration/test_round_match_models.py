import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Entry, Event, Match, MatchResult, Pod, Round


def _make_pod_with_two_entries(db_session) -> tuple[Pod, Entry, Entry]:
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    entry1 = Entry(
        pod_id=pod.id, player_uuid=uuid.uuid4(), source_system="club-checkin", metadata_={}
    )
    entry2 = Entry(
        pod_id=pod.id, player_uuid=uuid.uuid4(), source_system="club-checkin", metadata_={}
    )
    db_session.add_all([entry1, entry2])
    db_session.flush()
    return pod, entry1, entry2


def test_match_defaults_to_unreported(db_session):
    pod, entry1, entry2 = _make_pod_with_two_entries(db_session)
    round_ = Round(pod_id=pod.id, number=1)
    db_session.add(round_)
    db_session.flush()

    match = Match(round_id=round_.id, entry1_id=entry1.id, entry2_id=entry2.id)
    db_session.add(match)
    db_session.commit()

    assert match.result == MatchResult.UNREPORTED
    assert match.reported_by is None
    assert match.confirmed_by == []


def test_round_number_unique_per_pod(db_session):
    pod, _entry1, _entry2 = _make_pod_with_two_entries(db_session)
    db_session.add(Round(pod_id=pod.id, number=1))
    db_session.commit()

    db_session.add(Round(pod_id=pod.id, number=1))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_match_requires_existing_round(db_session):
    _pod, entry1, entry2 = _make_pod_with_two_entries(db_session)
    match = Match(round_id=uuid.uuid4(), entry1_id=entry1.id, entry2_id=entry2.id)
    db_session.add(match)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_match_requires_existing_entry1(db_session):
    pod, _entry1, entry2 = _make_pod_with_two_entries(db_session)
    round_ = Round(pod_id=pod.id, number=1)
    db_session.add(round_)
    db_session.flush()

    match = Match(round_id=round_.id, entry1_id=uuid.uuid4(), entry2_id=entry2.id)
    db_session.add(match)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_match_allows_null_entry2_for_bye(db_session):
    pod, entry1, _entry2 = _make_pod_with_two_entries(db_session)
    round_ = Round(pod_id=pod.id, number=1)
    db_session.add(round_)
    db_session.flush()

    match = Match(round_id=round_.id, entry1_id=entry1.id, entry2_id=None)
    db_session.add(match)
    db_session.commit()

    assert match.id is not None
    assert match.entry2_id is None
