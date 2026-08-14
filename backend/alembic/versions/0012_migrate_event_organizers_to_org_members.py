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
            SELECT gen_random_uuid(), organization_id, player_uuid, source_system,
                   'organizer', now()
            FROM (
                -- Dedup identities across multiple events in the same org
                -- first: with ON CONFLICT DO UPDATE (unlike DO NOTHING),
                -- Postgres errors ("cannot affect row a second time") if the
                -- same conflict target appears more than once within one
                -- INSERT command.
                SELECT DISTINCT e.organization_id, eo.player_uuid, eo.source_system
                FROM event_organizers eo
                JOIN events e ON e.id = eo.event_id
            ) legacy_organizers
            ON CONFLICT ON CONSTRAINT uq_org_member_identity
            DO UPDATE SET role = 'organizer'
            WHERE organization_members.role NOT IN ('owner', 'organizer')
            """
        )
    )
    # Any org with zero OWNER rows after synthesis (e.g. 0011's placeholder
    # "Unassigned" org, which never gets an OrganizationMember row) is
    # permanently locked out of member management — both add and revoke are
    # gated by require_org_owner, which needs an existing OWNER row, and no
    # such row can ever be created once locked. Promote the earliest legacy
    # organizer (by event_organizers.created_at, since every synthesized row
    # above shares the same now() timestamp and can't be used for ordering)
    # to OWNER for any such org.
    conn.execute(
        sa.text(
            """
            WITH candidate AS (
                SELECT DISTINCT ON (e.organization_id) om.id AS member_id
                FROM event_organizers eo
                JOIN events e ON e.id = eo.event_id
                JOIN organization_members om
                    ON om.organization_id = e.organization_id
                    AND om.player_uuid = eo.player_uuid
                    AND om.source_system = eo.source_system
                WHERE NOT EXISTS (
                    SELECT 1 FROM organization_members om2
                    WHERE om2.organization_id = e.organization_id AND om2.role = 'owner'
                )
                ORDER BY e.organization_id, eo.created_at ASC
            )
            UPDATE organization_members
            SET role = 'owner'
            FROM candidate
            WHERE organization_members.id = candidate.member_id
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
