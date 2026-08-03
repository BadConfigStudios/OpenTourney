import uuid

from pydantic import BaseModel, ConfigDict, Field


class EntryCreate(BaseModel):
    pod_id: uuid.UUID
    player_uuid: uuid.UUID
    source_system: str
    metadata: dict = {}


class EntryUpdate(BaseModel):
    metadata: dict


class EntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pod_id: uuid.UUID
    player_uuid: uuid.UUID
    source_system: str
    metadata: dict = Field(validation_alias="metadata_")
