import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Pod(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One tournament instance within an Event — the unit a
    `TournamentFormat` (`format_slug`, e.g. ``"swiss"``) and `GameModule`
    (`game_slug`, e.g. ``"generic"``) actually run against.

    `completed_at` is set when the organizer concludes the pod (see
    `POST /pods/{pod_id}/complete`); a completed pod's final standings are
    available via `GET /pods/{pod_id}/report`.
    """

    __tablename__ = "pods"
    __table_args__ = (UniqueConstraint("event_id", name="uq_pod_event"),)

    event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("events.id"), nullable=False
    )
    format_slug: Mapped[str] = mapped_column(nullable=False)
    game_slug: Mapped[str] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
