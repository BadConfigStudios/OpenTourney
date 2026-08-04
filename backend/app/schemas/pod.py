import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PodCreate(BaseModel):
    event_id: uuid.UUID
    format_slug: str
    game_slug: str


class PodUpdate(BaseModel):
    format_slug: str
    game_slug: str


class PodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    format_slug: str
    game_slug: str
    completed_at: datetime | None
