from app.games.base import GameModule


class GenericGameModule(GameModule):
    slug = "generic"

    def validate_entry_metadata(self, metadata: dict) -> None:
        return None
