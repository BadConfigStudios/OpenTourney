import uuid
from collections.abc import Sequence

from app.models import Entry, Round
from app.tiebreak._shared import average, opponents_faced, points_and_rounds_played
from app.tiebreak.base import TiebreakStrategy


class OwpOomwTiebreak(TiebreakStrategy):
    def __init__(
        self,
        floor: float = 0.33,
        win_points: int = 3,
        tie_points: int = 1,
        loss_points: int = 0,
    ):
        self.floor = floor
        self.win_points = win_points
        self.tie_points = tie_points
        self.loss_points = loss_points

    def compute(
        self, entries: Sequence[Entry], rounds: Sequence[Round]
    ) -> dict[uuid.UUID, tuple[float, float]]:
        points, rounds_played = points_and_rounds_played(
            rounds, self.win_points, self.tie_points, self.loss_points
        )
        opponents = opponents_faced(rounds)

        own_mwp = {
            entry.id: self._own_mwp(points.get(entry.id, 0), rounds_played.get(entry.id, 0))
            for entry in entries
        }
        omw_pct = {
            entry.id: average(own_mwp, opponents.get(entry.id, []), self.floor)
            for entry in entries
        }
        oomw_pct = {
            entry.id: average(omw_pct, opponents.get(entry.id, []), self.floor)
            for entry in entries
        }

        return {entry.id: (omw_pct[entry.id], oomw_pct[entry.id]) for entry in entries}

    def _own_mwp(self, points: int, rounds_played: int) -> float:
        if rounds_played == 0:
            return 0.0
        return max(points / (self.win_points * rounds_played), self.floor)

    def labels(self) -> tuple[str, str]:
        return ("OMW%", "OOMW%")
