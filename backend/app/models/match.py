import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MatchResult(enum.Enum):
    UNREPORTED = "unreported"
    ENTRY1_WIN = "entry1_win"
    ENTRY2_WIN = "entry2_win"
    TIE = "tie"


class Match(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "matches"

    round_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rounds.id"), nullable=False
    )
    entry1_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entries.id"), nullable=False
    )
    entry2_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entries.id"), nullable=True
    )
    result: Mapped[MatchResult] = mapped_column(
        Enum(
            MatchResult,
            name="match_result",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=MatchResult.UNREPORTED,
    )
    reported_by: Mapped[str | None] = mapped_column(String, nullable=True)
    witnessed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    confirmed_by: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
