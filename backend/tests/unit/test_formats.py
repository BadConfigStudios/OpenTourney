import uuid

import pytest

from app.formats.base import Pairing, TournamentFormat


def test_tournament_format_is_abstract():
    with pytest.raises(TypeError):
        TournamentFormat()


def test_concrete_format_implements_generate_round():
    class StubFormat(TournamentFormat):
        slug = "stub"

        def generate_round(self, entries, previous_rounds):
            return [Pairing(entry1_id=uuid.uuid4(), entry2_id=None)]

    pairings = StubFormat().generate_round(entries=[], previous_rounds=[])

    assert len(pairings) == 1
    assert pairings[0].entry2_id is None
