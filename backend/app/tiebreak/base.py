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
        entry's own matches) so a future Family B strategy can read any
        player's own round-by-round result sequence, not only opponents'
        final records.
        """
