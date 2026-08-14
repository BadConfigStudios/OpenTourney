# Phase 12 — RBAC Cutover to Org Membership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire `EventOrganizer` as the authorization mechanism across events/pods/entries/rounds/matches and resolve organizer access purely through `Organization`/`OrganizationMember` (Phase 11's data model), closing the two gaps flagged in issue #72 (OWNER visibility of org-mate-created events; member revocation).

**Architecture:** `event_organizer_exists` (the single choke point every `require_event_organizer`/`require_pod_organizer`/`pod_access_allowed`/`pod_staff_allowed` call composes) swaps its `EventOrganizer` lookup for an `OrganizationMember` role check (`OWNER`/`ORGANIZER` on the event's org). `visible_event_ids` gains the same org-role join in place of the `EventOrganizer` id set. One Alembic migration synthesizes `OrganizationMember` rows from every surviving `EventOrganizer` row before dropping `event_organizers`, so no pre-existing event (including those in Phase 11's placeholder "Unassigned" org) loses its organizer mid-cutover. `EventOrganizer` the model/table is deleted once nothing references it. Two new endpoints (`GET`/`DELETE /organizations/{id}/members`) close the revocation gap.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 ORM, Alembic, pytest + testcontainers (`postgres:16`), Pydantic schemas.

## Global Constraints

- Full design at `docs/superpowers/specs/2026-08-13-phase-12-rbac-cutover-design.md` — every task below implements a section of it; re-read a section if a step here seems underspecified.
- "Organizer" = org role `OWNER` or `ORGANIZER` on the event's `organization_id`. `SCOREKEEPER`/`JUDGE` org roles confer nothing extra at pod/entry/round/match level (unchanged, reserved for a future phase).
- `PodRole`/`PodRoleName` are untouched — independent grant mechanism, out of scope.
- No frontend changes — confirmed zero `EventOrganizer`/organizer references in `frontend/src`.
- Final state (end of Task 2): `grep -rn "EventOrganizer\|event_organizer" backend/` returns nothing outside migration `0012`'s historical SQL/downgrade block and this plan/design doc's own prose.
- Branch: `feat/phase-12-rbac-cutover` (worktree already exists and is checked out). Commit after every task's final green test run.

---

### Task 1: Migration 0012 + auth dependency cutover + events.py dual-write removal

This is the atomic core of the cutover: the migration drops `event_organizers`, so the dependency-layer read path and the one router write path must land in the same commit set as the migration — there is no valid intermediate state where the table is gone but `event_organizer_exists`/`create_event` still query the ORM `EventOrganizer` model against it.

**Files:**
- Create: `backend/alembic/versions/0012_migrate_event_organizers_to_org_members.py`
- Create: `backend/tests/integration/test_migration_0012.py`
- Modify: `backend/app/auth/dependencies.py:44-54` (`event_organizer_exists`), `:102-120` (`visible_event_ids`)
- Modify: `backend/app/routers/events.py:1-52` (imports, `create_event` dual-write), `:108-124` (`delete_event` cleanup line)
- Modify: `backend/tests/integration/test_auth_dependencies.py` (fixture rework, `EventOrganizer` → `OrganizationMember`)
- Modify: `backend/tests/integration/test_rbac_models.py` (drop the three `EventOrganizer`-specific tests; `EventOrganizer` table is gone as of this task)
- Modify: `backend/tests/integration/test_events_api.py` (add two new tests closing issue #72 item 2)

**Interfaces:**
- Consumes: `app.models.organization.Organization`, `OrganizationMember`, `OrgRoleName` (Phase 11, existing). `app.auth.dependencies.org_member_role(db, identity, organization_id) -> OrgRoleName | None` (existing, unchanged signature).
- Produces: `event_organizer_exists(db, identity, event_id) -> bool` and `visible_event_ids(db, identity) -> set[uuid.UUID]` keep their existing signatures — every downstream caller (`require_event_organizer`, `require_pod_organizer`, `pod_access_allowed`, `pod_staff_allowed`, `require_pod_access`, `events.py`) is unchanged and inherits the new behavior for free.

- [ ] **Step 1: Write the standalone migration test (RED)**

Mirrors `test_migration_0011_backfills_preexisting_events` in `backend/tests/integration/test_organization_model.py` — its own container, stops the migration chain short of 0012, seeds pre-0012 rows, then upgrades and asserts.

```python
# backend/tests/integration/test_migration_0012.py
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
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && pytest tests/integration/test_migration_0012.py -v`
Expected: FAIL — `alembic upgrade 0012` errors, revision `0012` doesn't exist yet.

- [ ] **Step 3: Write migration 0012**

```python
# backend/alembic/versions/0012_migrate_event_organizers_to_org_members.py
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
```

- [ ] **Step 4: Run the migration test to confirm it passes**

Run: `cd backend && pytest tests/integration/test_migration_0012.py -v`
Expected: PASS

- [ ] **Step 5: Commit the migration**

```bash
git add backend/alembic/versions/0012_migrate_event_organizers_to_org_members.py backend/tests/integration/test_migration_0012.py
git commit -m "feat(backend): add migration 0012 synthesizing org_members from event_organizers"
```

- [ ] **Step 6: Rework `test_auth_dependencies.py` fixtures onto `OrganizationMember` (still RED — dependencies.py not yet changed)**

The shared `db_session`/`migrated_engine` fixture now migrates to head (0012), so `event_organizers` no longer exists — every `EventOrganizer(...)` construction in this file must become an `OrganizationMember(organization_id=event.organization_id, ..., role=OrgRoleName.ORGANIZER)`. Replace the import and every construction site:

```python
# top of file, replace:
from app.models.rbac import EventOrganizer, PodRole, PodRoleName
# with:
from app.models.organization import OrganizationMember, OrgRoleName
from app.models.rbac import PodRole, PodRoleName
```

Replace each of the 5 `EventOrganizer(event_id=..., player_uuid=..., source_system="club-checkin")` construction sites (lines ~145, ~191, ~291, ~329 plus the comment at ~294) with:

```python
OrganizationMember(
    organization_id=event.organization_id,  # or event_a.organization_id at the ~291 site
    player_uuid=player_uuid,
    source_system="club-checkin",
    role=OrgRoleName.ORGANIZER,
)
```

At the `~291` site (`test_visible_event_ids_unions_organizer_and_pod_role_events`), also update the trailing comment `# Pod role on a pod belonging to event B (no EventOrganizer row for B).` to `# Pod role on a pod belonging to event B (no org membership on B's org for this identity).`

- [ ] **Step 7: Run the file to confirm it still fails**

Run: `cd backend && pytest tests/integration/test_auth_dependencies.py -v`
Expected: FAIL on the organizer/visibility tests — `event_organizer_exists`/`visible_event_ids` still query the (now-gone) `EventOrganizer` table, so these will error with `UndefinedTable`, not just assert-fail.

- [ ] **Step 8: Rework `test_rbac_models.py` — drop the three `EventOrganizer` tests**

Delete `test_event_organizer_persists`, `test_event_organizer_rejects_duplicate_identity_per_event`, `test_event_organizer_requires_existing_event`, and the `EventOrganizer` import (keep `PodRole`, `PodRoleName`, and the `_make_event`/`_make_pod` helpers — still used by the `PodRole` tests below them):

```python
from app.models.rbac import PodRole, PodRoleName
```

- [ ] **Step 9: Run the file to confirm it passes (nothing left in it references the dropped table)**

Run: `cd backend && pytest tests/integration/test_rbac_models.py -v`
Expected: PASS

- [ ] **Step 10: Rewrite `event_organizer_exists` in `backend/app/auth/dependencies.py`**

```python
def event_organizer_exists(db: Session, identity: Identity, event_id: uuid.UUID) -> bool:
    event = db.get(Event, event_id)
    if event is None:
        return False
    role = org_member_role(db, identity, event.organization_id)
    return role in (OrgRoleName.OWNER, OrgRoleName.ORGANIZER)
```

- [ ] **Step 11: Rewrite `visible_event_ids` in the same file**

```python
def visible_event_ids(db: Session, identity: Identity) -> set[uuid.UUID]:
    org_role_rows = (
        db.query(Event.id)
        .join(OrganizationMember, OrganizationMember.organization_id == Event.organization_id)
        .filter(
            OrganizationMember.player_uuid == identity.player_uuid,
            OrganizationMember.source_system == identity.source_system,
            OrganizationMember.role.in_((OrgRoleName.OWNER, OrgRoleName.ORGANIZER)),
        )
    )
    org_event_ids = {row.id for row in org_role_rows}
    pod_ids = {
        row.pod_id
        for row in db.query(PodRole.pod_id).filter_by(
            player_uuid=identity.player_uuid, source_system=identity.source_system
        )
    }
    pod_event_ids = (
        {row.event_id for row in db.query(Pod.event_id).filter(Pod.id.in_(pod_ids))}
        if pod_ids
        else set()
    )
    return org_event_ids | pod_event_ids
```

- [ ] **Step 12: Update the file's import block**

`event_organizer_exists`/`visible_event_ids` no longer touch `EventOrganizer`. Replace:

```python
from app.models.rbac import EventOrganizer, PodRole, PodRoleName
```

with:

```python
from app.models.rbac import PodRole, PodRoleName
```

(`Organization`, `OrganizationMember`, `OrgRoleName` are already imported at the top of this file from Phase 11's `require_org_owner`/`org_member_role` — no new import needed there.)

- [ ] **Step 13: Run `test_auth_dependencies.py` to confirm it now passes**

Run: `cd backend && pytest tests/integration/test_auth_dependencies.py -v`
Expected: PASS

- [ ] **Step 14: Remove the `EventOrganizer` dual-write from `events.py`'s `create_event`**

The creator's access is already guaranteed — `create_event` requires `org_member_role(...) in (OWNER, ORGANIZER)` before it ever creates the `Event`, and that same membership row is now the sole source of truth `event_organizer_exists` reads. Change:

```python
    event = Event(
        date=payload.date,
        name=payload.name,
        description=payload.description,
        organization_id=payload.organization_id,
    )
    db.add(event)
    db.flush()
    db.add(
        EventOrganizer(
            event_id=event.id,
            player_uuid=identity.player_uuid,
            source_system=identity.source_system,
        )
    )
    db.commit()
    db.refresh(event)
    return event
```

to:

```python
    event = Event(
        date=payload.date,
        name=payload.name,
        description=payload.description,
        organization_id=payload.organization_id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
```

- [ ] **Step 15: Remove the `EventOrganizer` cleanup line from `delete_event`**

Nothing left to clean up — the table is gone. Change:

```python
    for pod in db.query(Pod).filter_by(event_id=event_id).all():
        delete_pod_children(db, pod.id)
        db.delete(pod)
    db.query(EventOrganizer).filter_by(event_id=event_id).delete()
    db.delete(event)
    db.commit()
```

to:

```python
    for pod in db.query(Pod).filter_by(event_id=event_id).all():
        delete_pod_children(db, pod.id)
        db.delete(pod)
    db.delete(event)
    db.commit()
```

- [ ] **Step 16: Drop the now-unused `EventOrganizer` import from `events.py`**

Remove `from app.models.rbac import EventOrganizer` from the top of `backend/app/routers/events.py`.

- [ ] **Step 17: Add the two visibility-gap regression tests to `test_events_api.py`**

Closes issue #72 item 2 — an org OWNER can now operate on an event an org-mate ORGANIZER created, and vice versa.

```python
def test_org_owner_can_operate_on_event_created_by_org_organizer(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)

    staff_uuid = str(uuid.uuid4())
    api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )
    staff_token = make_token(
        player_uuid=uuid.UUID(staff_uuid), source_system="club-checkin", roles=["organizer"]
    )
    create_response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Staff-Created Event", "organization_id": org_id},
        headers=_auth_headers(staff_token),
    )
    event_id = create_response.json()["id"]

    get_response = api_client.get(f"/events/{event_id}", headers=_auth_headers(owner_token))
    patch_response = api_client.patch(
        f"/events/{event_id}", json={"name": "Renamed by Owner"}, headers=_auth_headers(owner_token)
    )

    assert get_response.status_code == 200
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Renamed by Owner"


def test_org_organizer_can_operate_on_event_created_by_org_owner(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    create_response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Owner-Created Event", "organization_id": org_id},
        headers=_auth_headers(owner_token),
    )
    event_id = create_response.json()["id"]

    staff_uuid = str(uuid.uuid4())
    api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )
    staff_token = make_token(
        player_uuid=uuid.UUID(staff_uuid), source_system="club-checkin", roles=["organizer"]
    )

    get_response = api_client.get(f"/events/{event_id}", headers=_auth_headers(staff_token))
    patch_response = api_client.patch(
        f"/events/{event_id}", json={"name": "Renamed by Organizer"}, headers=_auth_headers(staff_token)
    )

    assert get_response.status_code == 200
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Renamed by Organizer"
```

- [ ] **Step 18: Run the full backend suite**

Run: `cd backend && pytest -v`
Expected: PASS, all tests including the two new ones and the migration test.

- [ ] **Step 19: Commit**

```bash
git add backend/app/auth/dependencies.py backend/app/routers/events.py backend/tests/integration/test_auth_dependencies.py backend/tests/integration/test_rbac_models.py backend/tests/integration/test_events_api.py
git commit -m "feat(backend): resolve organizer access via OrganizationMember instead of EventOrganizer"
```

---

### Task 2: Remove the `EventOrganizer` model and verify no references remain

Pure cleanup — nothing queries `EventOrganizer` after Task 1; this removes the now-dead ORM class and its export.

**Files:**
- Modify: `backend/app/models/rbac.py` (remove `EventOrganizer` class)
- Modify: `backend/app/models/__init__.py` (remove `EventOrganizer` import/export)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — this is a deletion-only task, no other task depends on its output beyond the final grep check.

- [ ] **Step 1: Remove the `EventOrganizer` class from `backend/app/models/rbac.py`**

Delete the entire class (currently lines 20-35, between `PodRoleName` and `PodRole`):

```python
class EventOrganizer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Grants one external identity (`player_uuid` + `source_system`,
    NFR4) organizer rights over an Event — create/update Pods and Entries,
    generate rounds, complete the event."""

    __tablename__ = "event_organizers"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "player_uuid", "source_system", name="uq_event_organizer_identity"
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("events.id"), nullable=False
    )
    player_uuid: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(nullable=False)
```

Also drop the now-orphaned `PodRole` docstring reference to it — change:

```python
class PodRole(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Grants one external identity a `PodRoleName` role scoped to a
    single Pod, independent of any `EventOrganizer` grant on the parent
    Event."""
```

to:

```python
class PodRole(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Grants one external identity a `PodRoleName` role scoped to a
    single Pod, independent of any organizer-level grant on the parent
    Event."""
```

- [ ] **Step 2: Update `backend/app/models/__init__.py`**

```python
from app.models.base import Base
from app.models.entry import Entry
from app.models.event import Event
from app.models.match import Match, MatchResult
from app.models.organization import Organization, OrganizationMember, OrgRoleName
from app.models.pod import Pod
from app.models.rbac import PodRole, PodRoleName
from app.models.round import Round

__all__ = [
    "Base",
    "Entry",
    "Event",
    "Match",
    "MatchResult",
    "Organization",
    "OrganizationMember",
    "OrgRoleName",
    "Pod",
    "PodRole",
    "PodRoleName",
    "Round",
]
```

- [ ] **Step 3: Run the full backend suite**

Run: `cd backend && pytest -v`
Expected: PASS

- [ ] **Step 4: Final grep verification**

Run: `grep -rn "EventOrganizer\|event_organizer" backend/`
Expected: matches only inside `backend/alembic/versions/0012_migrate_event_organizers_to_org_members.py` (the SQL string and downgrade's table name) — nothing in `backend/app/` or `backend/tests/` outside that migration file.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/rbac.py backend/app/models/__init__.py
git commit -m "chore(backend): remove EventOrganizer model, superseded by OrganizationMember"
```

---

### Task 3: Organization member list/revoke endpoints (issue #72 item 1)

Mirrors `backend/app/routers/pod_roles.py`'s `list_pod_roles`/`revoke_pod_role` pattern. `GET` requires only membership (any role); `DELETE` requires `OWNER` (reuses the existing `require_org_owner` dependency).

**Files:**
- Modify: `backend/app/routers/organizations.py` (add `list_organization_members`, `revoke_organization_member`)
- Modify: `backend/tests/integration/test_organizations_api.py` (or create it if it doesn't exist — check first)

**Interfaces:**
- Consumes: `app.auth.dependencies.get_current_identity`, `require_org_owner`, `org_member_role` (all existing, unchanged). `app.schemas.organization.OrganizationMemberRead` (existing, unchanged — already has `id`, `organization_id`, `player_uuid`, `source_system`, `role`).
- Produces: `GET /organizations/{organization_id}/members -> list[OrganizationMemberRead]`, `DELETE /organizations/{organization_id}/members/{member_id} -> 204`.

- [ ] **Step 1: Check for an existing organizations API test file**

Run: `find backend/tests -iname "*organizations_api*"`

If it exists, read it fully before writing new tests (match its existing fixture/helper style, e.g. `_auth_headers`/`_create_org` helpers already established in `test_events_api.py`). If it doesn't exist, create `backend/tests/integration/test_organizations_api.py` with the same `_auth_headers`/`_create_org` helpers duplicated at the top (matching the pattern already used in `test_events_api.py` — these are small per-file test helpers in this codebase, not shared across files).

- [ ] **Step 2: Write the failing tests**

```python
import uuid

from app.models import Organization, OrganizationMember, OrgRoleName


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_org(api_client, token, name="Test Org") -> str:
    return api_client.post(
        "/organizations", json={"name": name}, headers=_auth_headers(token)
    ).json()["id"]


def test_owner_can_list_members(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    staff_uuid = str(uuid.uuid4())
    api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )

    response = api_client.get(f"/organizations/{org_id}/members", headers=_auth_headers(owner_token))

    assert response.status_code == 200
    roles = {row["role"] for row in response.json()}
    assert roles == {"owner", "organizer"}


def test_non_member_cannot_list_members(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.get(
        f"/organizations/{org_id}/members", headers=_auth_headers(stranger_token)
    )

    assert response.status_code == 403


def test_list_members_404s_for_unknown_org(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.get(f"/organizations/{uuid.uuid4()}/members", headers=_auth_headers(token))

    assert response.status_code == 404


def test_owner_can_revoke_member(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    staff_uuid = str(uuid.uuid4())
    add_response = api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )
    member_id = add_response.json()["id"]

    delete_response = api_client.delete(
        f"/organizations/{org_id}/members/{member_id}", headers=_auth_headers(owner_token)
    )
    list_response = api_client.get(f"/organizations/{org_id}/members", headers=_auth_headers(owner_token))

    assert delete_response.status_code == 204
    assert len(list_response.json()) == 1


def test_non_owner_cannot_revoke_member(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    staff_uuid = str(uuid.uuid4())
    add_response = api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )
    member_id = add_response.json()["id"]
    staff_token = make_token(
        player_uuid=uuid.UUID(staff_uuid), source_system="club-checkin", roles=["organizer"]
    )

    response = api_client.delete(
        f"/organizations/{org_id}/members/{member_id}", headers=_auth_headers(staff_token)
    )

    assert response.status_code == 403


def test_revoke_404s_for_member_not_belonging_to_org(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    other_org_id = _create_org(api_client, owner_token, name="Other Org")
    staff_uuid = str(uuid.uuid4())
    add_response = api_client.post(
        f"/organizations/{other_org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )
    member_id = add_response.json()["id"]

    response = api_client.delete(
        f"/organizations/{org_id}/members/{member_id}", headers=_auth_headers(owner_token)
    )

    assert response.status_code == 404


def test_revoked_member_loses_event_access(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    staff_uuid = str(uuid.uuid4())
    add_response = api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )
    member_id = add_response.json()["id"]
    staff_token = make_token(
        player_uuid=uuid.UUID(staff_uuid), source_system="club-checkin", roles=["organizer"]
    )
    event_response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Staff Event", "organization_id": org_id},
        headers=_auth_headers(staff_token),
    )
    event_id = event_response.json()["id"]

    api_client.delete(
        f"/organizations/{org_id}/members/{member_id}", headers=_auth_headers(owner_token)
    )
    response = api_client.get(f"/events/{event_id}", headers=_auth_headers(staff_token))

    assert response.status_code == 403
```

- [ ] **Step 3: Run the tests to confirm they fail**

Run: `cd backend && pytest tests/integration/test_organizations_api.py -v`
Expected: FAIL — `GET`/`DELETE /organizations/{id}/members*` routes don't exist yet (404 "Not Found" from FastAPI's default handler, not the application's own 404).

- [ ] **Step 4: Add the two endpoints to `backend/app/routers/organizations.py`**

Append to the end of the file, and add `get_current_identity`'s already-imported name plus a small ad hoc "any member" check inline (no new dependency needed — the existing `get_current_identity` plus a direct `org_member_role` call is enough, matching how `require_org_owner` itself is built):

```python
@router.get("/{organization_id}/members", response_model=list[OrganizationMemberRead])
def list_organization_members(
    organization_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> list[OrganizationMember]:
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="organization not found")
    if org_member_role(db, identity, organization_id) is None:
        raise HTTPException(status_code=403, detail="membership on this organization required")
    return (
        db.query(OrganizationMember)
        .filter_by(organization_id=organization_id)
        .order_by(OrganizationMember.id)
        .all()
    )


@router.delete("/{organization_id}/members/{member_id}", status_code=204)
def revoke_organization_member(
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    identity: Identity = Depends(require_org_owner),
    db: Session = Depends(get_db_session),
) -> None:
    member = db.get(OrganizationMember, member_id)
    if member is None or member.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="organization member not found")
    db.delete(member)
    db.commit()
```

Add `org_member_role` to the existing import line at the top of the file:

```python
from app.auth.dependencies import (
    get_current_identity,
    org_member_role,
    require_organizer_claim,
    require_org_owner,
)
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `cd backend && pytest tests/integration/test_organizations_api.py -v`
Expected: PASS

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && pytest -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/organizations.py backend/tests/integration/test_organizations_api.py
git commit -m "feat(backend): add GET/DELETE organizations/{id}/members endpoints"
```

---

## Self-Review Notes

- **Spec coverage**: §3 (auth logic) → Task 1 Steps 10-11. §4 (routers) → Task 1 Steps 14-17 (events.py) and Task 3 (organizations.py); `pods.py`/`entries.py`/`rounds.py`/`pod_roles.py`/`matches.py` need no changes per design, confirmed no task touches them. §5 (migration) → Task 1 Steps 1-5. §6 (issue #72 disposition) → item 1 is Task 3, item 2 is Task 1 Step 17, items 3-4 confirmed out of scope (no task touches `NewEvent.tsx` or `nginx.conf`). §7 (testing) → migration test (Task 1), auth dependency + events API tests (Task 1), organizations API tests (Task 3), final grep (Task 2 Step 4).
- **Placeholder scan**: none found — every step has literal code or an exact command.
- **Type consistency**: `event_organizer_exists`/`visible_event_ids` signatures unchanged across all call sites; `OrganizationMemberRead` schema reused as-is for the new `GET` endpoint (no new schema needed, confirmed by reading `backend/app/schemas/organization.py`).
