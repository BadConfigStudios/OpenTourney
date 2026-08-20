import pytest

from app.games.base import GameModule
from app.games.generic import GenericGameModule
from app.games.pokemon import PokemonGameModule


def test_game_module_is_abstract():
    with pytest.raises(TypeError):
        GameModule()


def test_generic_game_module_accepts_any_metadata():
    module = GenericGameModule()

    module.validate_entry_metadata({"anything": "goes"})
    module.validate_entry_metadata({})

    assert module.slug == "generic"


def test_pokemon_game_module_accepts_metadata_without_decklist_url():
    module = PokemonGameModule()

    module.validate_entry_metadata({})
    module.validate_entry_metadata({"display_name": "Ash"})

    assert module.slug == "pokemon-tcg"


def test_pokemon_game_module_accepts_limitless_shared_url():
    module = PokemonGameModule()

    module.validate_entry_metadata(
        {"decklist_url": "https://my.limitlesstcg.com/shared/69f80675a2d4f984ff635738"}
    )


def test_pokemon_game_module_accepts_limitless_decks_list_url():
    module = PokemonGameModule()

    module.validate_entry_metadata({"decklist_url": "https://limitlesstcg.com/decks/list/28236"})


def test_pokemon_game_module_rejects_wrong_host():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata({"decklist_url": "https://evil.example.com/shared/123"})


def test_pokemon_game_module_rejects_wrong_path():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata(
            {"decklist_url": "https://my.limitlesstcg.com/tournament/123"}
        )


def test_pokemon_game_module_rejects_http_scheme():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata(
            {"decklist_url": "http://my.limitlesstcg.com/shared/69f80675a2d4f984ff635738"}
        )


def test_pokemon_game_module_rejects_non_string_decklist_url():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata({"decklist_url": 12345})


def test_pokemon_game_module_rejects_empty_id():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata({"decklist_url": "https://limitlesstcg.com/decks/list/"})


def test_pokemon_game_module_rejects_multi_segment_path():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata(
            {"decklist_url": "https://limitlesstcg.com/decks/list/28236/extra"}
        )


def test_pokemon_game_module_rejects_query_string():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata(
            {"decklist_url": "https://limitlesstcg.com/decks/list/28236?foo=bar"}
        )


def test_pokemon_game_module_rejects_fragment():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata(
            {"decklist_url": "https://limitlesstcg.com/decks/list/28236#anchor"}
        )


def test_pokemon_game_module_rejects_leading_whitespace():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata(
            {"decklist_url": " https://limitlesstcg.com/decks/list/28236"}
        )


def test_pokemon_game_module_rejects_embedded_tab():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata(
            {"decklist_url": "https://limitlesstcg.com/decks/list/\t28236"}
        )


def test_pokemon_game_module_rejects_malformed_url_with_friendly_message():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata({"decklist_url": "https://[abc/shared/x"})


def test_pokemon_match_points_match_handbook_defaults():
    assert PokemonGameModule.WIN_POINTS == 3
    assert PokemonGameModule.TIE_POINTS == 1
    assert PokemonGameModule.LOSS_POINTS == 0
