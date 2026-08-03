import pytest

from app.games.generic import GenericGameModule
from app.games.registry import get_game_module


def test_get_game_module_returns_generic_module():
    module = get_game_module("generic")

    assert isinstance(module, GenericGameModule)


def test_get_game_module_raises_for_unknown_slug():
    with pytest.raises(ValueError, match="unknown game module slug"):
        get_game_module("pokemon-tcg")
