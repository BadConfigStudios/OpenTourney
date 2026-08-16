import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.organization import OrgRoleName


def _reject_blank_name(name: str) -> str:
    if not name.strip():
        raise ValueError("name must not be blank")
    return name


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1)

    _reject_blank_name = field_validator("name")(_reject_blank_name)


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=1)

    _reject_blank_name = field_validator("name")(_reject_blank_name)


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
