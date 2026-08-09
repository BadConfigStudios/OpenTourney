import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.match import Match


class Round(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One generated round of pairings within a Pod's Swiss sequence.

    `number` is 1-indexed and unique per pod. `matches` holds every
    pairing generated for this round, including byes (a `Match` with
    `entry2_id is None`), ordered by insertion.
    """

    __tablename__ = "rounds"
    __table_args__ = (UniqueConstraint("pod_id", "number", name="uq_round_number_per_pod"),)

    pod_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pods.id"), nullable=False
    )
    number: Mapped[int] = mapped_column(nullable=False)
    matches: Mapped[list["Match"]] = relationship(order_by="Match.id")
