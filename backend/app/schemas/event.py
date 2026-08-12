import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class EventCreate(BaseModel):
    date: dt.date
    name: str
    description: str | None = None
    organization_id: uuid.UUID


class EventUpdate(BaseModel):
    date: dt.date
    name: str
    description: str | None = None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: dt.date
    name: str
    description: str | None
    organization_id: uuid.UUID
