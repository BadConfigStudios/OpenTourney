from app.games.base import GameModule
from app.games.generic import GenericGameModule

GAME_MODULES: dict[str, GameModule] = {
    "generic": GenericGameModule(),
}


def get_game_module(slug: str) -> GameModule:
    try:
        return GAME_MODULES[slug]
    except KeyError:
        raise ValueError(f"unknown game module slug: {slug!r}") from None
