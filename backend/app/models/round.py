import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Round(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "rounds"
    __table_args__ = (UniqueConstraint("pod_id", "number", name="uq_round_number_per_pod"),)

    pod_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pods.id"), nullable=False
    )
    number: Mapped[int] = mapped_column(nullable=False)
