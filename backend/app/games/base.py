from abc import ABC, abstractmethod

from app.tiebreak.base import TiebreakStrategy


class GameModule(ABC):
    slug: str

    @abstractmethod
    def validate_entry_metadata(self, metadata: dict) -> None:
        """Raise ValueError if metadata is invalid for this game."""

    @abstractmethod
    def tiebreak_strategy(self) -> TiebreakStrategy:
        """Return this game's TiebreakStrategy for Swiss standings/ranking."""
