import os
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from testcontainers.community.postgres import PostgresContainer

from app.models import Organization, OrganizationMember, OrgRoleName

BACKEND_DIR = Path(__file__).resolve().parents[2]
PLACEHOLDER_ORG_ID = "00000000-0000-0000-0000-000000000001"


def test_organization_persists(db_session):
    org = Organization(name="Dragon's Den")
    db_session.add(org)
    db_session.commit()

    assert org.id is not None
    assert org.name == "Dragon's Den"


def test_organization_member_persists_with_role(db_session):
    org = Organization(name="Dragon's Den")
    db_session.add(org)
    db_session.flush()

    member = OrganizationMember(
        organization_id=org.id,
        player_uuid=uuid.uuid4(),
        source_system="club-checkin",
        role=OrgRoleName.OWNER,
    )
    db_session.add(member)
    db_session.commit()

    assert member.id is not None
    assert member.role == OrgRoleName.OWNER


def test_organization_member_rejects_duplicate_identity_in_same_org(db_session):
    org = Organization(name="Dragon's Den")
    db_session.add(org)
    db_session.flush()
    player_uuid = uuid.uuid4()

    db_session.add(
        OrganizationMember(
            organization_id=org.id,
            player_uuid=player_uuid,
            source_system="club-checkin",
            role=OrgRoleName.OWNER,
        )
    )
    db_session.commit()

    db_session.add(
        OrganizationMember(
            organization_id=org.id,
            player_uuid=player_uuid,
            source_system="club-checkin",
            role=OrgRoleName.ORGANIZER,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_organization_member_requires_existing_organization(db_session):
    member = OrganizationMember(
        organization_id=uuid.uuid4(),
        player_uuid=uuid.uuid4(),
        source_system="club-checkin",
        role=OrgRoleName.OWNER,
    )
    db_session.add(member)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_migration_0011_backfills_preexisting_events():
    """Regression coverage for migration 0011's backfill UPDATEs.

    `migrated_engine` always upgrades a fresh database straight to `head`,
    so it can never exercise the `WHERE ... IS NULL` backfill branches —
    those only run against rows that existed *before* 0011 added the
    `name`/`organization_id` columns. This test builds that scenario for
    real: migrate to 0010, insert a raw `events` row using the pre-0011
    column set, migrate to 0011, and assert the row was backfilled with
    the placeholder Organization and 'Untitled Event'.

    Uses its own Postgres container (rather than the session-scoped
    `postgres_url`/`migrated_engine` fixtures) because it needs to stop
    the migration chain at 0010 before continuing to 0011.
    """
    with PostgresContainer("postgres:16", driver="psycopg") as postgres:
        db_url = postgres.get_connection_url()
        env = {**os.environ, "DATABASE_URL": db_url}

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "0010"],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
        )

        pre_existing_event_id = uuid.uuid4()
        engine = create_engine(db_url)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO events (id, date, created_at) VALUES (:id, :date, now())"),
                    {"id": pre_existing_event_id, "date": date(2026, 1, 1)},
                )
        finally:
            engine.dispose()

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "0011"],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
        )

        engine = create_engine(db_url)
        try:
            with engine.connect() as conn:
                event_row = conn.execute(
                    text("SELECT organization_id, name FROM events WHERE id = :id"),
                    {"id": pre_existing_event_id},
                ).one()
                org_row = conn.execute(
                    text("SELECT id, name FROM organizations WHERE id = :id"),
                    {"id": PLACEHOLDER_ORG_ID},
                ).one()
        finally:
            engine.dispose()

    assert str(event_row.organization_id) == PLACEHOLDER_ORG_ID
    assert event_row.name == "Untitled Event"
    assert str(org_row.id) == PLACEHOLDER_ORG_ID
    assert org_row.name == "Unassigned"
