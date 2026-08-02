import pytest

from app.games.base import GameModule
from app.games.generic import GenericGameModule


def test_game_module_is_abstract():
    with pytest.raises(TypeError):
        GameModule()


def test_generic_game_module_accepts_any_metadata():
    module = GenericGameModule()

    module.validate_entry_metadata({"anything": "goes"})
    module.validate_entry_metadata({})

    assert module.slug == "generic"
