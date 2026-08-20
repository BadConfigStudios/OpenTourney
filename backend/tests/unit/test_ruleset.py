import uuid

import pytest
from fastapi import HTTPException

from app.formats.swiss import SwissFormat
from app.games.pokemon import PokemonGameModule
from app.models import Pod
from app.ruleset import Ruleset, get_ruleset_or_422
from app.tiebreak.owp_oomw import OwpOomwTiebreak
from app.tiebreak.pokemon import PokemonTiebreak


def _pod(format_slug: str, game_slug: str) -> Pod:
    return Pod(id=uuid.uuid4(), event_id=uuid.uuid4(), format_slug=format_slug, game_slug=game_slug)


def test_resolves_swiss_generic_to_owp_oomw():
    ruleset = get_ruleset_or_422(_pod("swiss", "generic"))

    assert isinstance(ruleset, Ruleset)
    assert isinstance(ruleset.format, SwissFormat)
    assert isinstance(ruleset.format.tiebreak, OwpOomwTiebreak)


def test_resolves_swiss_pokemon_to_pokemon_tiebreak():
    ruleset = get_ruleset_or_422(_pod("swiss", "pokemon-tcg"))

    assert isinstance(ruleset.format, SwissFormat)
    assert isinstance(ruleset.format.tiebreak, PokemonTiebreak)
    assert isinstance(ruleset.game_module, PokemonGameModule)


def test_unrecognized_game_slug_raises_422():
    with pytest.raises(HTTPException) as exc_info:
        get_ruleset_or_422(_pod("swiss", "not-a-real-game"))

    assert exc_info.value.status_code == 422


def test_unrecognized_format_slug_raises_422():
    with pytest.raises(HTTPException) as exc_info:
        get_ruleset_or_422(_pod("not-a-real-format", "generic"))

    assert exc_info.value.status_code == 422
