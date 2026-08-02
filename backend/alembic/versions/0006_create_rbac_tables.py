"""create rbac tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# create_type=False keeps op.create_table() from re-emitting its own CREATE TYPE for this
# enum; the type is created explicitly below via pod_role_name_enum.create(), matching the
# pattern in 0004_create_round_and_match.py.
pod_role_name_enum = postgresql.ENUM(
    "scorekeeper",
    "user",
    name="pod_role_name",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "event_organizers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=False
        ),
        sa.Column("player_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "event_id", "player_uuid", "source_system", name="uq_event_organizer_identity"
        ),
    )
    op.create_index("ix_event_organizers_event_id", "event_organizers", ["event_id"])

    pod_role_name_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "pod_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "pod_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pods.id"), nullable=False
        ),
        sa.Column("player_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column("role", pod_role_name_enum, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "pod_id", "player_uuid", "source_system", name="uq_pod_role_identity"
        ),
    )
    op.create_index("ix_pod_roles_pod_id", "pod_roles", ["pod_id"])


def downgrade() -> None:
    op.drop_table("pod_roles")
    pod_role_name_enum.drop(op.get_bind(), checkfirst=True)
    op.drop_table("event_organizers")
