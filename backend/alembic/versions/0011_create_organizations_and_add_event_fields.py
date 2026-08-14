"""create organizations and add event name/description/organization_id

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

# create_type=False keeps op.create_table() from re-emitting its own CREATE TYPE for this
# enum; the type is created explicitly below via org_role_name_enum.create(), matching the
# pattern in 0006_create_rbac_tables.py.
org_role_name_enum = postgresql.ENUM(
    "owner",
    "organizer",
    "scorekeeper",
    "judge",
    name="org_role_name",
    create_type=False,
)

PLACEHOLDER_ORG_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    org_role_name_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "organization_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("player_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(), nullable=False),
        sa.Column("role", org_role_name_enum, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "organization_id", "player_uuid", "source_system", name="uq_org_member_identity"
        ),
    )
    op.create_index(
        "ix_organization_members_organization_id", "organization_members", ["organization_id"]
    )
    op.create_index(
        "ix_organization_members_player_source",
        "organization_members",
        ["player_uuid", "source_system"],
    )

    op.add_column("events", sa.Column("name", sa.String(), nullable=True))
    op.add_column("events", sa.Column("description", sa.String(), nullable=True))
    op.add_column(
        "events",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_events_organization_id", "events", ["organization_id"])

    conn = op.get_bind()
    # Only insert the placeholder org and backfill pre-existing rows if any
    # `events` rows actually exist yet. On a brand-new database (zero rows),
    # skipping this leaves no orphan "Unassigned" Organization behind — the
    # subsequent alter_column(..., nullable=False) calls are correct either
    # way since there are no rows to violate the constraint.
    if conn.execute(sa.text("SELECT count(*) FROM events")).scalar():
        conn.execute(
            sa.text(
                "INSERT INTO organizations (id, name, created_at) VALUES (:id, :name, now())"
            ),
            {"id": PLACEHOLDER_ORG_ID, "name": "Unassigned"},
        )
        conn.execute(
            sa.text("UPDATE events SET organization_id = :org_id WHERE organization_id IS NULL"),
            {"org_id": PLACEHOLDER_ORG_ID},
        )
        conn.execute(sa.text("UPDATE events SET name = 'Untitled Event' WHERE name IS NULL"))

    op.alter_column("events", "name", nullable=False)
    op.alter_column("events", "organization_id", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_events_organization_id", table_name="events")
    op.drop_column("events", "organization_id")
    op.drop_column("events", "description")
    op.drop_column("events", "name")

    op.drop_index("ix_organization_members_player_source", table_name="organization_members")
    op.drop_index("ix_organization_members_organization_id", table_name="organization_members")
    op.drop_table("organization_members")
    org_role_name_enum.drop(op.get_bind(), checkfirst=True)

    op.drop_table("organizations")
