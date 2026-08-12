import enum
import uuid

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A store/league/venue that hosts Events. Organizer rights on an
    Event are granted once at the Organization level (`OrganizationMember`)
    rather than per-event, so adding or removing staff doesn't require
    touching every event individually."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(nullable=False)


class OrgRoleName(str, enum.Enum):
    """Roles grantable within an Organization. `JUDGE` has no enforced
    capability difference from `ORGANIZER` yet — reserved for a future
    phase (e.g. penalty issuance) once that feature exists."""

    OWNER = "owner"
    ORGANIZER = "organizer"
    SCOREKEEPER = "scorekeeper"
    JUDGE = "judge"


class OrganizationMember(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Grants one external identity (`player_uuid` + `source_system`,
    NFR4) a role within an Organization."""

    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "player_uuid", "source_system", name="uq_org_member_identity"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    player_uuid: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(nullable=False)
    role: Mapped[OrgRoleName] = mapped_column(
        Enum(
            OrgRoleName,
            name="org_role_name",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
