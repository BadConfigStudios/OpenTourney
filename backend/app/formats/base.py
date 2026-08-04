import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from app.models import Entry, Round


@dataclass(frozen=True)
class Pairing:
    entry1_id: uuid.UUID
    entry2_id: uuid.UUID | None  # None means a bye
    table_number: int | None = None


@dataclass(frozen=True)
class StandingRow:
    entry_id: uuid.UUID
    points: int
    rank: int


class TournamentFormat(ABC):
    slug: str

    @abstractmethod
    def generate_round(
        self, entries: Sequence[Entry], previous_rounds: Sequence[Round]
    ) -> list[Pairing]:
        """Return this pod's next round's pairings given its entries and completed prior rounds."""

    @abstractmethod
    def compute_standings(
        self, entries: Sequence[Entry], rounds: Sequence[Round]
    ) -> list[StandingRow]:
        """Return ranked standings for all entries given completed rounds."""
