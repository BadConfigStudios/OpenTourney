import uuid

from pydantic import BaseModel


class StandingRowRead(BaseModel):
    entry_id: uuid.UUID
    points: int
    rank: int
    tiebreakers: list[float]


class PodReport(BaseModel):
    is_complete: bool
    rounds_played: int
    is_partial: bool
    standings: list[StandingRowRead]
