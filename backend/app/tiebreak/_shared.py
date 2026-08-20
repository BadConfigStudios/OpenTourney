import uuid
from collections.abc import Sequence

from app.models import MatchResult, Round


def points_and_rounds_played(
    rounds: Sequence[Round],
    win_points: int,
    tie_points: int,
    loss_points: int,
    include_bye: bool = True,
) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    """Tally match points and rounds-played per entry across `rounds`.

    `include_bye` controls whether a bye round contributes to the
    recipient's points numerator *and* rounds-played denominator for the
    purposes of this specific win%/MWP figure:

    - `True` (default, used by `OwpOomwTiebreak`): the existing MTG-style
      behavior — a bye is a normal played win, contributing `win_points`
      to the numerator and one round to the denominator, unaffected by
      this parameter's introduction.
    - `False` (used by `PokemonTiebreak`): a bye contributes to *neither*
      the numerator nor the denominator of the own-win% figure used as an
      input to *other* competitors' Op Win%/Op Op Win% averages — i.e.
      only the entry's actually-played (non-bye) rounds count toward this
      figure. This does NOT affect the entry's own primary standings
      points (see `app.formats.swiss._compute_standings`, which still
      counts a bye as a win for ranking purposes) — it is scoped entirely
      to the tiebreak-value calculation. This was empirically corrected
      against real Tournament Operations Manager (TOM) tournament data
      during Phase 18 implementation; see
      docs/pokemon-tiebreak-research.md §3 for the full reconciliation.
    """
    points: dict[uuid.UUID, int] = {}
    rounds_played: dict[uuid.UUID, int] = {}

    for round_ in rounds:
        for match in round_.matches:
            if match.entry2_id is None:
                if include_bye:
                    points[match.entry1_id] = points.get(match.entry1_id, 0) + win_points
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
