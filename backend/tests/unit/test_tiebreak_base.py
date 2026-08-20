import uuid

import pytest

from app.tiebreak.base import TiebreakStrategy


class _MinimalStrategy(TiebreakStrategy):
    def compute(self, entries, rounds):
        return {}

    def labels(self):
        return ("Stat A", "Stat B")


def test_tiebreak_strategy_is_abstract():
    with pytest.raises(TypeError):
        TiebreakStrategy()


def test_labels_is_required_by_subclasses():
    class _NoLabels(TiebreakStrategy):
        def compute(self, entries, rounds):
            return {}

    with pytest.raises(TypeError):
        _NoLabels()


def test_break_tie_defaults_to_none():
    strategy = _MinimalStrategy()

    result = strategy.break_tie(uuid.uuid4(), uuid.uuid4(), rounds=[])

    assert result is None
