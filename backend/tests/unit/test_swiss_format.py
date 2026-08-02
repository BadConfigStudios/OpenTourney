import uuid

from app.formats.swiss import SwissFormat
from app.models import Entry


def _entry() -> Entry:
    return Entry(
        id=uuid.uuid4(),
        pod_id=uuid.uuid4(),
        player_uuid=uuid.uuid4(),
        source_system="test",
        metadata_={},
    )


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
