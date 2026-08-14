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
    assert member_rows[0].role == "organizer"
