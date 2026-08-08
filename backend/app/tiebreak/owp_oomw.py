import uuid
from collections.abc import Sequence

from app.models import Entry, MatchResult, Round
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
        points, rounds_played = self._points_and_rounds_played(rounds)
        opponents = self._opponents_faced(rounds)

        own_mwp = {
            entry.id: self._own_mwp(points.get(entry.id, 0), rounds_played.get(entry.id, 0))
            for entry in entries
        }
        omw_pct = {
            entry.id: self._average(own_mwp, opponents.get(entry.id, []))
            for entry in entries
        }
        oomw_pct = {
            entry.id: self._average(omw_pct, opponents.get(entry.id, []))
            for entry in entries
        }

        return {entry.id: (omw_pct[entry.id], oomw_pct[entry.id]) for entry in entries}

    def _own_mwp(self, points: int, rounds_played: int) -> float:
        if rounds_played == 0:
            return 0.0
        return max(points / (self.win_points * rounds_played), self.floor)

    def _average(self, values: dict[uuid.UUID, float], opponent_ids: list[uuid.UUID]) -> float:
        if not opponent_ids:
            return self.floor
        return sum(values[opponent_id] for opponent_id in opponent_ids) / len(opponent_ids)

    def _points_and_rounds_played(
        self, rounds: Sequence[Round]
    ) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
        points: dict[uuid.UUID, int] = {}
        rounds_played: dict[uuid.UUID, int] = {}

        for round_ in rounds:
            for match in round_.matches:
                if match.entry2_id is None:
                    points[match.entry1_id] = points.get(match.entry1_id, 0) + self.win_points
                    rounds_played[match.entry1_id] = rounds_played.get(match.entry1_id, 0) + 1
                    continue

                rounds_played[match.entry1_id] = rounds_played.get(match.entry1_id, 0) + 1
                rounds_played[match.entry2_id] = rounds_played.get(match.entry2_id, 0) + 1

                if match.result is MatchResult.ENTRY1_WIN:
                    points[match.entry1_id] = points.get(match.entry1_id, 0) + self.win_points
                    points[match.entry2_id] = points.get(match.entry2_id, 0) + self.loss_points
                elif match.result is MatchResult.ENTRY2_WIN:
                    points[match.entry2_id] = points.get(match.entry2_id, 0) + self.win_points
                    points[match.entry1_id] = points.get(match.entry1_id, 0) + self.loss_points
                elif match.result is MatchResult.TIE:
                    points[match.entry1_id] = points.get(match.entry1_id, 0) + self.tie_points
                    points[match.entry2_id] = points.get(match.entry2_id, 0) + self.tie_points
                else:
                    raise ValueError(f"round {round_.number} has an unreported match")

        return points, rounds_played

    @staticmethod
    def _opponents_faced(rounds: Sequence[Round]) -> dict[uuid.UUID, list[uuid.UUID]]:
        opponents: dict[uuid.UUID, list[uuid.UUID]] = {}

        for round_ in rounds:
            for match in round_.matches:
                if match.entry2_id is None:
                    continue
                opponents.setdefault(match.entry1_id, []).append(match.entry2_id)
                opponents.setdefault(match.entry2_id, []).append(match.entry1_id)

        return opponents
