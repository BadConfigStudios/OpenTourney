import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MatchResult(str, enum.Enum):
    """A match's outcome. `UNREPORTED` until a result is submitted via
    `POST /matches/{match_id}/result`; terminal values are the two win
    outcomes and `TIE` (draw)."""

    UNREPORTED = "unreported"
    ENTRY1_WIN = "entry1_win"
    ENTRY2_WIN = "entry2_win"
    TIE = "tie"


class Match(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single pairing between two entries within a Round.

    `entry2_id` is nullable — `None` marks a bye (`entry1_id` receives an
    automatic win, no result reporting required). `confirmed_by` is a
    JSONB audit-trail list recording who confirmed the reported result;
    `reported_by`/`witnessed_by` are set from the reporting identity's
    `source_system:player_uuid` (see `report_match_result`).
    """

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
            # values_callable sends the enum's .value (lowercase) to Postgres instead of
            # the default .name, which must match the lowercase labels of the DB enum type.
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=MatchResult.UNREPORTED,
    )
    method: Mapped[str] = mapped_column(String, nullable=False, default="manual_entry")
    reported_by: Mapped[str | None] = mapped_column(String, nullable=True)
    witnessed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    confirmed_by: Mapped[list] = mapped_column(
        MutableList.as_mutable(JSONB), nullable=False, default=list
    )
    table_number: Mapped[int | None] = mapped_column(nullable=True)
