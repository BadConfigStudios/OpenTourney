from app.games.base import GameModule
from app.games.generic import GenericGameModule
from app.games.pokemon import PokemonGameModule

GAME_MODULES: dict[str, GameModule] = {
    "generic": GenericGameModule(),
    "pokemon-tcg": PokemonGameModule(),
}


def get_game_module(slug: str) -> GameModule:
    try:
        return GAME_MODULES[slug]
    except KeyError:
        raise ValueError(f"unknown game module slug: {slug!r}") from None
