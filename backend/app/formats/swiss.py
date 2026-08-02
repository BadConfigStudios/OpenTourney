from collections.abc import Sequence

from app.formats.base import Pairing, TournamentFormat
from app.models import Entry, Round

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

        raise NotImplementedError("subsequent-round pairing lands in Task 4/5")


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
