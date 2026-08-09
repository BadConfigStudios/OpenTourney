import enum
import uuid

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PodRoleName(str, enum.Enum):
    """Roles grantable within a single Pod. `SCOREKEEPER` may report match
    results; `USER` is a non-privileged grant (currently unused by any
    authorization check, reserved for future use)."""

    SCOREKEEPER = "scorekeeper"
    USER = "user"


class EventOrganizer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Grants one external identity (`player_uuid` + `source_system`,
    NFR4) organizer rights over an Event — create/update Pods and Entries,
    generate rounds, complete the event."""

    __tablename__ = "event_organizers"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "player_uuid", "source_system", name="uq_event_organizer_identity"
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("events.id"), nullable=False
    )
    player_uuid: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(nullable=False)


class PodRole(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Grants one external identity a `PodRoleName` role scoped to a
    single Pod, independent of any `EventOrganizer` grant on the parent
    Event."""

    __tablename__ = "pod_roles"
    __table_args__ = (
        UniqueConstraint("pod_id", "player_uuid", "source_system", name="uq_pod_role_identity"),
    )

    pod_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pods.id"), nullable=False
    )
    player_uuid: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(nullable=False)
    role: Mapped[PodRoleName] = mapped_column(
        Enum(
            PodRoleName,
            name="pod_role_name",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
