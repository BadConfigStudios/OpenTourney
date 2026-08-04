import uuid

from pydantic import BaseModel, ConfigDict

from app.schemas.match import MatchRead


class RoundRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pod_id: uuid.UUID
    number: int
    matches: list[MatchRead]
