import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Pod(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "pods"

    event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("events.id"), nullable=False
    )
    format_slug: Mapped[str] = mapped_column(nullable=False)
    game_slug: Mapped[str] = mapped_column(nullable=False)
