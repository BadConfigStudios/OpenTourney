from dataclasses import dataclass

from fastapi import HTTPException

from app.formats.base import TournamentFormat
from app.formats.swiss import SwissFormat
from app.games.base import GameModule
from app.games.registry import get_game_module
from app.models import Pod


@dataclass(frozen=True)
class Ruleset:
    format: TournamentFormat
    game_module: GameModule


def get_ruleset_or_422(pod: Pod) -> Ruleset:
    """Resolve pod's (format_slug, game_slug) into a Ruleset, or raise HTTPException(422)."""
    if pod.format_slug != "swiss":
        raise HTTPException(
            status_code=422,
            detail=f"pod's format_slug {pod.format_slug!r} is not a recognized tournament format",
        )

    try:
        game_module = get_game_module(pod.game_slug)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"pod's game_slug {pod.game_slug!r} is not a recognized game module",
        ) from exc

    tournament_format = SwissFormat(tiebreak=game_module.tiebreak_strategy())
    return Ruleset(format=tournament_format, game_module=game_module)
