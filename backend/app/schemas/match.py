import uuid

from pydantic import BaseModel, ConfigDict

from app.models import MatchResult


class MatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    round_id: uuid.UUID
    entry1_id: uuid.UUID
    entry2_id: uuid.UUID | None
    result: MatchResult
    reported_by: str | None
    witnessed_by: str | None
    table_number: int | None
