import uuid

from pydantic import BaseModel, ConfigDict

from app.models.rbac import PodRoleName


class PodRoleCreate(BaseModel):
    player_uuid: uuid.UUID
    source_system: str
    role: PodRoleName


class PodRoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pod_id: uuid.UUID
    player_uuid: uuid.UUID
    source_system: str
    role: PodRoleName
