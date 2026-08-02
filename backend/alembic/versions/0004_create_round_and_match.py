"""create round and match tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# create_type=False keeps op.create_table() from re-emitting its own CREATE TYPE for this
# enum; the type is created explicitly below via match_result_enum.create(), and letting
# create_table() also emit it would collide and raise DuplicateObject.
match_result_enum = postgresql.ENUM(
    "unreported",
    "entry1_win",
    "entry2_win",
    "tie",
    name="match_result",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "rounds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "pod_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pods.id"), nullable=False
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("pod_id", "number", name="uq_round_number_per_pod"),
    )
    op.create_index("ix_rounds_pod_id", "rounds", ["pod_id"])

    match_result_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "round_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rounds.id"), nullable=False
        ),
        sa.Column(
            "entry1_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entries.id"),
            nullable=False,
        ),
        sa.Column(
            "entry2_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entries.id"), nullable=True
        ),
        sa.Column("result", match_result_enum, nullable=False, server_default="unreported"),
        sa.Column("reported_by", sa.String(), nullable=True),
        sa.Column("witnessed_by", sa.String(), nullable=True),
        sa.Column("confirmed_by", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_matches_round_id", "matches", ["round_id"])


def downgrade() -> None:
    op.drop_table("matches")
    match_result_enum.drop(op.get_bind(), checkfirst=True)
    op.drop_table("rounds")
