from fastapi import HTTPException

from app.formats.base import TournamentFormat
from app.formats.swiss import SwissFormat
from app.models import Pod

FORMATS: dict[str, TournamentFormat] = {
    "swiss": SwissFormat(),
}


def get_tournament_format(slug: str) -> TournamentFormat:
    try:
        return FORMATS[slug]
    except KeyError:
        raise ValueError(f"unknown tournament format slug: {slug!r}") from None


def get_tournament_format_or_422(pod: Pod) -> TournamentFormat:
    """Look up pod's tournament format, or raise HTTPException(422) if unrecognized."""
    try:
        return get_tournament_format(pod.format_slug)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"pod's format_slug {pod.format_slug!r} is not a recognized tournament format",
        ) from exc
