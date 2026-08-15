import uuid

from pydantic import BaseModel, ConfigDict

from app.models.organization import OrgRoleName


class OrganizationCreate(BaseModel):
    name: str


class OrganizationUpdate(BaseModel):
    name: str


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class OrganizationDetailRead(OrganizationRead):
    viewer_role: OrgRoleName


class OrganizationMemberCreate(BaseModel):
    player_uuid: uuid.UUID
    source_system: str
    role: OrgRoleName


class OrganizationMemberUpdate(BaseModel):
    role: OrgRoleName


class OrganizationMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    player_uuid: uuid.UUID
    source_system: str
    role: OrgRoleName
