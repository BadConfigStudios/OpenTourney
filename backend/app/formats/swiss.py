from collections.abc import Sequence

from app.formats.base import Pairing, StandingRow, TournamentFormat
from app.models import Entry, MatchResult, Round

WIN_POINTS = 3
TIE_POINTS = 1
LOSS_POINTS = 0


class SwissFormat(TournamentFormat):
    slug = "swiss"

    def generate_round(
        self, entries: Sequence[Entry], previous_rounds: Sequence[Round]
    ) -> list[Pairing]:
        if not previous_rounds:
            return _pair_round_one(entries)

        standings, bye_used = _compute_standings(entries, previous_rounds)
        already_paired = _paired_history(previous_rounds)
        ranked = _rank_entries(entries, standings)

        bye_entry = None
        if len(ranked) % 2 == 1:
            bye_entry = _select_bye_entry(ranked, bye_used)
            ranked = [entry for entry in ranked if entry.id != bye_entry.id]

        pairings = _pair_remaining(ranked, already_paired)
        if bye_entry is not None:
            pairings.append(Pairing(entry1_id=bye_entry.id, entry2_id=None))

        return _assign_tables(pairings)

    def compute_standings(
        self, entries: Sequence[Entry], rounds: Sequence[Round]
    ) -> list[StandingRow]:
        standings, _ = _compute_standings(entries, rounds)
        ranked = _rank_entries(entries, standings)
        return [
            StandingRow(entry_id=entry.id, points=standings.get(entry.id, 0), rank=i + 1)
            for i, entry in enumerate(ranked)
        ]


def _compute_standings(
    entries: Sequence[Entry], previous_rounds: Sequence[Round]
) -> tuple[dict, set]:
    standings = {entry.id: 0 for entry in entries}
    bye_used = set()

    for round_ in previous_rounds:
        for match in round_.matches:
            if match.entry2_id is None:
                standings[match.entry1_id] = standings.get(match.entry1_id, 0) + WIN_POINTS
                bye_used.add(match.entry1_id)
                continue

            if match.result is MatchResult.ENTRY1_WIN:
                standings[match.entry1_id] = standings.get(match.entry1_id, 0) + WIN_POINTS
            elif match.result is MatchResult.ENTRY2_WIN:
                standings[match.entry2_id] = standings.get(match.entry2_id, 0) + WIN_POINTS
            elif match.result is MatchResult.TIE:
                standings[match.entry1_id] = standings.get(match.entry1_id, 0) + TIE_POINTS
                standings[match.entry2_id] = standings.get(match.entry2_id, 0) + TIE_POINTS
            else:
                # Catches UNREPORTED and also `None` (an unflushed Match whose
                # mapped_column default hasn't fired yet at INSERT time) — both
                # mean this match doesn't have a scoreable result.
                raise ValueError(f"round {round_.number} has an unreported match")

    return standings, bye_used


def _paired_history(previous_rounds: Sequence[Round]) -> set:
    paired = set()
    for round_ in previous_rounds:
        for match in round_.matches:
            if match.entry2_id is not None:
                paired.add(frozenset({match.entry1_id, match.entry2_id}))
    return paired


def _rank_entries(entries: Sequence[Entry], standings: dict) -> list:
    return sorted(entries, key=lambda entry: (-standings.get(entry.id, 0), str(entry.id)))


def _select_bye_entry(ranked: list, bye_used: set):
    for entry in reversed(ranked):
        if entry.id not in bye_used:
            return entry
    return ranked[-1]


def _pair_remaining(ranked: list, already_paired: set) -> list[Pairing]:
    remaining = list(ranked)
    pairings: list[Pairing] = []

    while remaining:
        entry1 = remaining.pop(0)
        partner_index = next(
            (
                i
                for i, candidate in enumerate(remaining)
                if frozenset({entry1.id, candidate.id}) not in already_paired
            ),
            # Greedy, no backtracking: an early pairing choice can strand later
            # entries into an avoidable rematch even when a rematch-free
            # pairing of the whole round exists. Known limitation, tracked in
            # https://github.com/BadConfigStudios/OpenTourney/issues/12.
            0,
        )
        entry2 = remaining.pop(partner_index)
        pairings.append(Pairing(entry1_id=entry1.id, entry2_id=entry2.id))

    return pairings


def _pair_round_one(entries: Sequence[Entry]) -> list[Pairing]:
    ordered = list(entries)
    pairings: list[Pairing] = []
    i = 0
    while i + 1 < len(ordered):
        pairings.append(Pairing(entry1_id=ordered[i].id, entry2_id=ordered[i + 1].id))
        i += 2
    if i < len(ordered):
        pairings.append(Pairing(entry1_id=ordered[i].id, entry2_id=None))
    return _assign_tables(pairings)


def _assign_tables(pairings: list[Pairing]) -> list[Pairing]:
    assigned: list[Pairing] = []
    table_number = 1
    for pairing in pairings:
        if pairing.entry2_id is None:
            assigned.append(pairing)
            continue
        assigned.append(
            Pairing(
                entry1_id=pairing.entry1_id,
                entry2_id=pairing.entry2_id,
                table_number=table_number,
            )
        )
        table_number += 1
    return assigned
