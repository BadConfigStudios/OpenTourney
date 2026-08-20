import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.models import Entry, Round


class TiebreakStrategy(ABC):
    @abstractmethod
    def compute(
        self, entries: Sequence[Entry], rounds: Sequence[Round]
    ) -> dict[uuid.UUID, tuple[float, ...]]:
        """Per-entry ordered tiebreak chain, most-significant value first.

        Receives ALL entries and the full round history (not just one
        entry's own matches) so a strategy can read any player's own
        round-by-round result sequence, not only opponents' final records.
        """

    @abstractmethod
    def labels(self) -> tuple[str, ...]:
        """Column labels matching compute()'s tuple order, most-significant first."""

    def break_tie(
        self, entry_a_id: uuid.UUID, entry_b_id: uuid.UUID, rounds: Sequence[Round]
    ) -> int | None:
        """Pairwise fallback for two entries tied after compute()'s chain.

        Returns -1 if entry_a_id ranks higher, 1 if entry_b_id ranks
        higher, or None if this strategy has no pairwise fallback (the
        default) or the fallback can't resolve this particular pair.
        """
        return None
