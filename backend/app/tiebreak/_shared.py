import uuid
from collections.abc import Sequence

from app.models import MatchResult, Round


def points_and_rounds_played(
    rounds: Sequence[Round],
    win_points: int,
    tie_points: int,
    loss_points: int,
    bye_rounds_played: bool = True,
) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    """Tally match points and rounds-played per entry across `rounds`.

    `bye_rounds_played` controls whether a bye round counts toward the
    recipient's rounds-played denominator: `True` for MTG-style own-MWP
    (OwpOomwTiebreak), `False` for Pokémon's own win% (PokemonTiebreak,
    handbook §5.6.1 — a bye counts as a win but not a played round).
    """
    points: dict[uuid.UUID, int] = {}
    rounds_played: dict[uuid.UUID, int] = {}

    for round_ in rounds:
        for match in round_.matches:
            if match.entry2_id is None:
                points[match.entry1_id] = points.get(match.entry1_id, 0) + win_points
                if bye_rounds_played:
                    rounds_played[match.entry1_id] = rounds_played.get(match.entry1_id, 0) + 1
                continue

            rounds_played[match.entry1_id] = rounds_played.get(match.entry1_id, 0) + 1
            rounds_played[match.entry2_id] = rounds_played.get(match.entry2_id, 0) + 1

            if match.result is MatchResult.ENTRY1_WIN:
                points[match.entry1_id] = points.get(match.entry1_id, 0) + win_points
                points[match.entry2_id] = points.get(match.entry2_id, 0) + loss_points
            elif match.result is MatchResult.ENTRY2_WIN:
                points[match.entry2_id] = points.get(match.entry2_id, 0) + win_points
                points[match.entry1_id] = points.get(match.entry1_id, 0) + loss_points
            elif match.result is MatchResult.TIE:
                points[match.entry1_id] = points.get(match.entry1_id, 0) + tie_points
                points[match.entry2_id] = points.get(match.entry2_id, 0) + tie_points
            else:
                raise ValueError(f"round {round_.number} has an unreported match")

    return points, rounds_played


def opponents_faced(rounds: Sequence[Round]) -> dict[uuid.UUID, list[uuid.UUID]]:
    opponents: dict[uuid.UUID, list[uuid.UUID]] = {}

    for round_ in rounds:
        for match in round_.matches:
            if match.entry2_id is None:
                continue
            opponents.setdefault(match.entry1_id, []).append(match.entry2_id)
            opponents.setdefault(match.entry2_id, []).append(match.entry1_id)

    return opponents


def average(values: dict[uuid.UUID, float], opponent_ids: list[uuid.UUID], floor: float) -> float:
    if not opponent_ids:
        return floor
    return sum(values[opponent_id] for opponent_id in opponent_ids) / len(opponent_ids)
