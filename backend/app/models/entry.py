import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Entry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "entries"
    __table_args__ = (
        UniqueConstraint(
            "pod_id", "player_uuid", "source_system", name="uq_entry_player_per_pod"
        ),
    )

    pod_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pods.id"), nullable=False
    )
    player_uuid: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(nullable=False)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", MutableDict.as_mutable(JSONB), nullable=False, default=dict
    )
