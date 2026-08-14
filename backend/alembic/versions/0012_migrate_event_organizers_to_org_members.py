"""synthesize organization_members from event_organizers, then drop event_organizers

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO organization_members
                (id, organization_id, player_uuid, source_system, role, created_at)
            SELECT gen_random_uuid(), e.organization_id, eo.player_uuid, eo.source_system,
                   'organizer', now()
            FROM event_organizers eo
            JOIN events e ON e.id = eo.event_id
            ON CONFLICT ON CONSTRAINT uq_org_member_identity DO NOTHING
            """
        )
    )
    op.drop_table("event_organizers")


def downgrade() -> None:
    # Recreates event_organizers empty, mirroring 0006's original definition
    # exactly. Synthesized OrganizationMember rows are NOT reverse-migrated
    # out — this is a schema-only revert, not a data revert.
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
    op.create_index(
        "ix_event_organizers_player_source", "event_organizers", ["player_uuid", "source_system"]
    )
