import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class EventCreate(BaseModel):
    date: dt.date


class EventUpdate(BaseModel):
    date: dt.date


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: dt.date
