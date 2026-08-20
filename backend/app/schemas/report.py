import uuid
from typing import Literal

from pydantic import BaseModel


class TiebreakValue(BaseModel):
    label: str
    value: float
    format: Literal["percent"]


class StandingRowRead(BaseModel):
    entry_id: uuid.UUID
    points: int
    rank: int
    tiebreakers: list[TiebreakValue]


class PodReport(BaseModel):
    is_complete: bool
    rounds_played: int
    is_partial: bool
    active_entry_count: int
    recommended_rounds: int
    standings: list[StandingRowRead]
