from app.games.base import GameModule
from app.tiebreak.base import TiebreakStrategy
from app.tiebreak.owp_oomw import OwpOomwTiebreak


class GenericGameModule(GameModule):
    slug = "generic"

    WIN_POINTS = 3
    TIE_POINTS = 1
    LOSS_POINTS = 0

    def validate_entry_metadata(self, metadata: dict) -> None:
        return None

    def tiebreak_strategy(self) -> TiebreakStrategy:
        return OwpOomwTiebreak(
            win_points=self.WIN_POINTS, tie_points=self.TIE_POINTS, loss_points=self.LOSS_POINTS
        )
