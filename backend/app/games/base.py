from abc import ABC, abstractmethod


class GameModule(ABC):
    slug: str

    @abstractmethod
    def validate_entry_metadata(self, metadata: dict) -> None:
        """Raise ValueError if metadata is invalid for this game."""
