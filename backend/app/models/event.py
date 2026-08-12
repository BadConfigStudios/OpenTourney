import datetime as dt
import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Event(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single-day in-person tournament event, identified by its name and date,
    and belonging to exactly one Organization.

    MVP1 restricts an Event to at most one Pod — see `Pod`'s
    `uq_pod_event` unique constraint.
    """

    __tablename__ = "events"

    # NOTE: the type is imported as `dt` (not `from datetime import date`)
    # because SQLAlchemy 2.0's annotation resolution re-evaluates `Mapped[date]`
    # against the class's own namespace; naming the column `date` would shadow
    # the imported `date` type and raise `MappedAnnotationError`.
    date: Mapped[dt.date] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(nullable=True, default=None)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
