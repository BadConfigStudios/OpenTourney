from urllib.parse import urlsplit

from app.games.base import GameModule
from app.tiebreak.base import TiebreakStrategy
from app.tiebreak.pokemon import PokemonTiebreak

_DECKLIST_URL_ERROR = (
    "decklist_url must be an https://my.limitlesstcg.com/shared/<id> or "
    "https://limitlesstcg.com/decks/list/<id> link"
)

_ALLOWED_DECKLIST_HOSTS = {
    "my.limitlesstcg.com": "/shared/",
    "limitlesstcg.com": "/decks/list/",
}


class PokemonGameModule(GameModule):
    """Pokemon TCG game module.

    Descriptive only -- no rules enforcement. Bo1-by-default reporting is
    organizer discretion per the Play! Pokemon Tournament Rules Handbook
    S5.5.6. Match points below match handbook S5.3.2 and drive
    PokemonTiebreak's Op Win%/Op Op Win% chain (Phase 18, FR28/FR29).
    """

    slug = "pokemon-tcg"

    WIN_POINTS = 3
    TIE_POINTS = 1
    LOSS_POINTS = 0

    def validate_entry_metadata(self, metadata: dict) -> None:
        decklist_url = metadata.get("decklist_url")
        if decklist_url is None:
            return
        if not isinstance(decklist_url, str):
            raise ValueError(_DECKLIST_URL_ERROR)

        if decklist_url != decklist_url.strip() or any(c.isspace() for c in decklist_url):
            raise ValueError(_DECKLIST_URL_ERROR)

        try:
            parts = urlsplit(decklist_url)
        except ValueError:
            raise ValueError(_DECKLIST_URL_ERROR) from None

        if parts.scheme != "https":
            raise ValueError(_DECKLIST_URL_ERROR)

        path_prefix = _ALLOWED_DECKLIST_HOSTS.get(parts.hostname or "")
        if path_prefix is None or not parts.path.startswith(path_prefix):
            raise ValueError(_DECKLIST_URL_ERROR)

        # Extract the ID portion after the prefix
        id_portion = parts.path[len(path_prefix) :]
        if not id_portion:
            raise ValueError(_DECKLIST_URL_ERROR)

        # ID must be a single segment with no further slashes
        if "/" in id_portion:
            raise ValueError(_DECKLIST_URL_ERROR)

        # Reject URLs with query strings or fragments
        if parts.query or parts.fragment:
            raise ValueError(_DECKLIST_URL_ERROR)

    def tiebreak_strategy(self) -> TiebreakStrategy:
        return PokemonTiebreak(
            win_points=self.WIN_POINTS, tie_points=self.TIE_POINTS, loss_points=self.LOSS_POINTS
        )
