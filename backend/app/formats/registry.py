from app.formats.base import TournamentFormat
from app.formats.swiss import SwissFormat

FORMATS: dict[str, TournamentFormat] = {
    "swiss": SwissFormat(),
}


def get_tournament_format(slug: str) -> TournamentFormat:
    try:
        return FORMATS[slug]
    except KeyError:
        raise ValueError(f"unknown tournament format slug: {slug!r}") from None
