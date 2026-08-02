import uuid

import pytest

from app.formats.swiss import SwissFormat, _compute_standings
from app.models import Entry, Match, MatchResult, Round


def _entry() -> Entry:
    return Entry(
        id=uuid.uuid4(),
        pod_id=uuid.uuid4(),
        player_uuid=uuid.uuid4(),
        source_system="test",
        metadata_={},
    )


def _round(number: int, matches: list[Match]) -> Round:
    round_ = Round(id=uuid.uuid4(), pod_id=uuid.uuid4(), number=number)
    round_.matches = matches
    return round_


def test_round_one_pairs_entries_sequentially_with_table_numbers():
    entries = [_entry(), _entry(), _entry(), _entry()]

    pairings = SwissFormat().generate_round(entries=entries, previous_rounds=[])

    assert len(pairings) == 2
    assert pairings[0].entry1_id == entries[0].id
    assert pairings[0].entry2_id == entries[1].id
    assert pairings[0].table_number == 1
    assert pairings[1].entry1_id == entries[2].id
    assert pairings[1].entry2_id == entries[3].id
    assert pairings[1].table_number == 2


def test_round_one_gives_bye_to_last_entry_when_odd():
    entries = [_entry(), _entry(), _entry()]

    pairings = SwissFormat().generate_round(entries=entries, previous_rounds=[])

    assert len(pairings) == 2
    bye = pairings[-1]
    assert bye.entry1_id == entries[2].id
    assert bye.entry2_id is None
    assert bye.table_number is None


def test_round_one_with_no_entries_returns_no_pairings():
    pairings = SwissFormat().generate_round(entries=[], previous_rounds=[])

    assert pairings == []


def test_compute_standings_awards_win_tie_loss_points():
    e1, e2, e3, e4 = _entry(), _entry(), _entry(), _entry()
    round1 = _round(
        1,
        [
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e1.id,
                entry2_id=e2.id,
                result=MatchResult.ENTRY1_WIN,
            ),
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e3.id,
                entry2_id=e4.id,
                result=MatchResult.TIE,
            ),
        ],
    )

    standings, bye_used = _compute_standings([e1, e2, e3, e4], [round1])

    assert standings[e1.id] == 3
    assert standings[e2.id] == 0
    assert standings[e3.id] == 1
    assert standings[e4.id] == 1
    assert bye_used == set()


def test_compute_standings_counts_bye_as_a_win():
    e1 = _entry()
    round1 = _round(
        1, [Match(id=uuid.uuid4(), round_id=uuid.uuid4(), entry1_id=e1.id, entry2_id=None)]
    )

    standings, bye_used = _compute_standings([e1], [round1])

    assert standings[e1.id] == 3
    assert bye_used == {e1.id}


def test_compute_standings_raises_on_unreported_match():
    e1, e2 = _entry(), _entry()
    round1 = _round(
        1,
        [
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e1.id,
                entry2_id=e2.id,
                result=MatchResult.UNREPORTED,
            )
        ],
    )

    with pytest.raises(ValueError, match="unreported"):
        _compute_standings([e1, e2], [round1])
