import uuid
from collections.abc import Sequence

from app.models import Entry, MatchResult, Round
from app.tiebreak._shared import average, opponents_faced, points_and_rounds_played
from app.tiebreak.base import TiebreakStrategy

FLOOR = 0.25
COMPLETED_CAP = 1.0
DROPPED_CAP = 0.75


class PokemonTiebreak(TiebreakStrategy):
    """Op Win% / Op Op Win% chain per Play! Pokémon Tournament Rules
    Handbook §5.3.3, §5.3.3.1, §5.5.1.1 — see docs/pokemon-tiebreak-research.md."""

    def __init__(self, win_points: int = 3, tie_points: int = 1, loss_points: int = 0):
        self.win_points = win_points
        self.tie_points = tie_points
        self.loss_points = loss_points

    def compute(
        self, entries: Sequence[Entry], rounds: Sequence[Round]
    ) -> dict[uuid.UUID, tuple[float, float]]:
        points, rounds_played = points_and_rounds_played(
            rounds,
            self.win_points,
            self.tie_points,
            self.loss_points,
            bye_rounds_played=False,
        )
        opponents = opponents_faced(rounds)
        dropped = {entry.id: entry.dropped_at_round is not None for entry in entries}

        own_win_pct = {
            entry.id: self._own_win_pct(
                points.get(entry.id, 0), rounds_played.get(entry.id, 0), dropped[entry.id]
            )
            for entry in entries
        }
        op_win_pct = {
            entry.id: average(own_win_pct, opponents.get(entry.id, []), FLOOR)
            for entry in entries
        }
        op_op_win_pct = {
            entry.id: average(op_win_pct, opponents.get(entry.id, []), FLOOR)
            for entry in entries
        }

        return {entry.id: (op_win_pct[entry.id], op_op_win_pct[entry.id]) for entry in entries}

    def _own_win_pct(self, points: int, rounds_played: int, dropped: bool) -> float:
        if rounds_played == 0:
            return FLOOR
        cap = DROPPED_CAP if dropped else COMPLETED_CAP
        raw = points / (self.win_points * rounds_played)
        return max(FLOOR, min(cap, raw))

    def labels(self) -> tuple[str, str]:
        return ("Op Win%", "Op Op Win%")

    def break_tie(
        self, entry_a_id: uuid.UUID, entry_b_id: uuid.UUID, rounds: Sequence[Round]
    ) -> int | None:
        return None  # implemented in Task 4
