import os
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, text
from testcontainers.community.postgres import PostgresContainer

BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_migration_0012_synthesizes_org_members_from_event_organizers():
    """`event_organizers` rows must become equivalent `OrganizationMember`
    rows before the table is dropped, so pre-existing events (including
    ones backfilled into Phase 11's placeholder "Unassigned" org) don't
    lose their organizers when 0012 removes the old grant table."""
    with PostgresContainer("postgres:16", driver="psycopg") as postgres:
        db_url = postgres.get_connection_url()
        env = {**os.environ, "DATABASE_URL": db_url}

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "0011"],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
        )

        org_id = uuid.uuid4()
        event_id = uuid.uuid4()
        organizer_uuid = uuid.uuid4()
        # Second EventOrganizer row for the same identity/org, to exercise
        # the ON CONFLICT DO NOTHING path (would otherwise violate
        # uq_org_member_identity).
        second_event_id = uuid.uuid4()

        engine = create_engine(db_url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO organizations (id, name, created_at) "
                        "VALUES (:id, 'Test Org', now())"
                    ),
                    {"id": org_id},
                )
                for eid in (event_id, second_event_id):
                    conn.execute(
                        text(
                            "INSERT INTO events (id, date, name, organization_id, created_at) "
                            "VALUES (:id, :date, 'Test Event', :org_id, now())"
                        ),
                        {"id": eid, "date": date(2026, 1, 1), "org_id": org_id},
                    )
                    conn.execute(
                        text(
                            "INSERT INTO event_organizers "
                            "(id, event_id, player_uuid, source_system, created_at) "
                            "VALUES (gen_random_uuid(), :event_id, :player_uuid, 'club-checkin', now())"
                        ),
                        {"event_id": eid, "player_uuid": organizer_uuid},
                    )
        finally:
            engine.dispose()

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "0012"],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
        )

        engine = create_engine(db_url)
        try:
            with engine.connect() as conn:
                member_rows = conn.execute(
                    text(
                        "SELECT organization_id, player_uuid, source_system, role "
                        "FROM organization_members WHERE player_uuid = :player_uuid"
                    ),
                    {"player_uuid": organizer_uuid},
                ).all()
                table_exists = conn.execute(
                    text(
                        "SELECT to_regclass('public.event_organizers') IS NOT NULL"
                    )
                ).scalar()
        finally:
            engine.dispose()

    assert table_exists is False
    assert len(member_rows) == 1
    assert str(member_rows[0].organization_id) == str(org_id)
    assert member_rows[0].source_system == "club-checkin"
    # This identity is the only (hence earliest) legacy organizer on an org
    # with zero OWNER rows, so it gets promoted to owner by the zero-owner
    # backfill step (Finding 1), not left at the synthesized 'organizer'.
    assert member_rows[0].role == "owner"


def test_migration_0012_promotes_earliest_organizer_to_owner_when_org_has_no_owner():
    """An org that ends up with zero OWNER rows after synthesis must not be
    permanently locked out of member management (both add and revoke require
    an existing OWNER row). The earliest legacy organizer, by the original
    event_organizers.created_at, gets promoted to owner; later ones stay
    organizer."""
    with PostgresContainer("postgres:16", driver="psycopg") as postgres:
        db_url = postgres.get_connection_url()
        env = {**os.environ, "DATABASE_URL": db_url}

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "0011"],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
        )

        org_id = uuid.uuid4()
        early_event_id = uuid.uuid4()
        late_event_id = uuid.uuid4()
        early_organizer_uuid = uuid.uuid4()
        late_organizer_uuid = uuid.uuid4()

        engine = create_engine(db_url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO organizations (id, name, created_at) "
                        "VALUES (:id, 'Owner Backfill Org', now())"
                    ),
                    {"id": org_id},
                )
                for eid in (early_event_id, late_event_id):
                    conn.execute(
                        text(
                            "INSERT INTO events (id, date, name, organization_id, created_at) "
                            "VALUES (:id, :date, 'Test Event', :org_id, now())"
                        ),
                        {"id": eid, "date": date(2026, 1, 1), "org_id": org_id},
                    )
                conn.execute(
                    text(
                        "INSERT INTO event_organizers "
                        "(id, event_id, player_uuid, source_system, created_at) "
                        "VALUES (gen_random_uuid(), :event_id, :player_uuid, 'club-checkin', "
                        "'2026-01-01T00:00:00Z')"
                    ),
                    {"event_id": early_event_id, "player_uuid": early_organizer_uuid},
                )
                conn.execute(
                    text(
                        "INSERT INTO event_organizers "
                        "(id, event_id, player_uuid, source_system, created_at) "
                        "VALUES (gen_random_uuid(), :event_id, :player_uuid, 'club-checkin', "
                        "'2026-02-01T00:00:00Z')"
                    ),
                    {"event_id": late_event_id, "player_uuid": late_organizer_uuid},
                )
        finally:
            engine.dispose()

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "0012"],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
        )

        engine = create_engine(db_url)
        try:
            with engine.connect() as conn:
                early_role = conn.execute(
                    text(
                        "SELECT role FROM organization_members "
                        "WHERE player_uuid = :player_uuid"
                    ),
                    {"player_uuid": early_organizer_uuid},
                ).scalar_one()
                late_role = conn.execute(
                    text(
                        "SELECT role FROM organization_members "
                        "WHERE player_uuid = :player_uuid"
                    ),
                    {"player_uuid": late_organizer_uuid},
                ).scalar_one()
        finally:
            engine.dispose()

    assert early_role == "owner"
    assert late_role == "organizer"


def test_migration_0012_upgrades_existing_lesser_role_to_organizer():
    """An identity that already holds a lesser OrganizationMember role (e.g.
    scorekeeper, added via the pre-existing add-member endpoint before this
    migration runs) and is also a legacy EventOrganizer on that org must be
    upgraded to organizer, not silently skipped by ON CONFLICT DO NOTHING."""
    with PostgresContainer("postgres:16", driver="psycopg") as postgres:
        db_url = postgres.get_connection_url()
        env = {**os.environ, "DATABASE_URL": db_url}

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "0011"],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
        )

        org_id = uuid.uuid4()
        event_id = uuid.uuid4()
        identity_uuid = uuid.uuid4()
        preexisting_owner_uuid = uuid.uuid4()

        engine = create_engine(db_url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO organizations (id, name, created_at) "
                        "VALUES (:id, 'Upgrade Org', now())"
                    ),
                    {"id": org_id},
                )
                conn.execute(
                    text(
                        "INSERT INTO events (id, date, name, organization_id, created_at) "
                        "VALUES (:id, :date, 'Test Event', :org_id, now())"
                    ),
                    {"id": event_id, "date": date(2026, 1, 1), "org_id": org_id},
                )
                # Pre-existing owner (e.g. the identity that created this org
                # via the app's create_organization flow), so the org
                # already has an OWNER row and Finding 1's zero-owner
                # backfill has nothing to do here — isolates this test to
                # Finding 2's upgrade behavior.
                conn.execute(
                    text(
                        "INSERT INTO organization_members "
                        "(id, organization_id, player_uuid, source_system, role, created_at) "
                        "VALUES (gen_random_uuid(), :org_id, :player_uuid, 'club-checkin', "
                        "'owner', now())"
                    ),
                    {"org_id": org_id, "player_uuid": preexisting_owner_uuid},
                )
                # Pre-existing scorekeeper membership, added via the
                # pre-cutover add-member endpoint.
                conn.execute(
                    text(
                        "INSERT INTO organization_members "
                        "(id, organization_id, player_uuid, source_system, role, created_at) "
                        "VALUES (gen_random_uuid(), :org_id, :player_uuid, 'club-checkin', "
                        "'scorekeeper', now())"
                    ),
                    {"org_id": org_id, "player_uuid": identity_uuid},
                )
                conn.execute(
                    text(
                        "INSERT INTO event_organizers "
                        "(id, event_id, player_uuid, source_system, created_at) "
                        "VALUES (gen_random_uuid(), :event_id, :player_uuid, 'club-checkin', now())"
                    ),
                    {"event_id": event_id, "player_uuid": identity_uuid},
                )
        finally:
            engine.dispose()

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "0012"],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
        )

        engine = create_engine(db_url)
        try:
            with engine.connect() as conn:
                role = conn.execute(
                    text(
                        "SELECT role FROM organization_members "
                        "WHERE player_uuid = :player_uuid"
                    ),
                    {"player_uuid": identity_uuid},
                ).scalar_one()
        finally:
            engine.dispose()

    assert role == "organizer"
