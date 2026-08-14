# Phase 11 — Organization Data Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `Organization`/`OrganizationMember` data model so organizer rights can be granted once at the org level instead of per-event, and give `Event` a real name/description instead of just a date.

**Architecture:** New `Organization`/`OrganizationMember` SQLAlchemy models + one Alembic migration (with a backfill for pre-existing `Event` rows); `Event` gains `name`/`description`/`organization_id`. `POST /events` gets one new inline authorization check (caller must be `OWNER`/`ORGANIZER` on the target org) but still dual-writes the existing `EventOrganizer` row, so every other router (pods/entries/rounds/matches) keeps working completely unchanged — the repo-wide RBAC cutover is a later phase, not this one.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, Pydantic (backend); React + TypeScript, TanStack Query, MSW/Vitest (frontend).

## Global Constraints

- `Organization`/`OrganizationMember` identity fields follow the existing external-identity pattern (NFR4): `player_uuid` + `source_system`, no local accounts.
- `OrgRoleName` has four values: `owner`, `organizer`, `scorekeeper`, `judge`. `judge` has zero enforced capability difference from `organizer` in this phase — it exists in the schema/API only.
- `POST /events` requires `organization_id`/`name` (`description` optional); caller must hold `OWNER` or `ORGANIZER` on that org, checked inline in the router (not a repo-wide RBAC cutover — every other router keeps calling `event_organizer_exists` exactly as today).
- `EventOrganizer` is still created on every successful `POST /events` (dual-write) — do not remove or bypass it in this phase.
- Migration backfill: pre-existing `Event` rows get a placeholder `Organization` (`name="Unassigned"`, fixed id `00000000-0000-0000-0000-000000000001`) and a placeholder `name` (`"Untitled Event"`) if missing, then both `events.name` and `events.organization_id` become `NOT NULL` in the same migration.
- Follow existing codebase patterns exactly: model mixins (`UUIDPrimaryKeyMixin`, `TimestampMixin`), the `Base, TimestampMixin, UUIDPrimaryKeyMixin` class signature, the `*Create`/`*Read` schema split, the private `_require_X` inline-check-in-router convention (see `entries.py`'s `_require_pod_event_organizer`), and the Postgres-enum migration pattern from `0006_create_rbac_tables.py`.

---

### Task 1: Data model — Organization, OrganizationMember, Event fields

**Files:**
- Create: `backend/app/models/organization.py`
- Modify: `backend/app/models/event.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0011_create_organizations_and_add_event_fields.py`
- Test: `backend/tests/integration/test_organization_model.py`

**Interfaces:**
- Produces: `Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin)` with `name: str`. `OrgRoleName(str, enum.Enum)` with `OWNER`/`ORGANIZER`/`SCOREKEEPER`/`JUDGE` (values `"owner"`/`"organizer"`/`"scorekeeper"`/`"judge"`). `OrganizationMember(Base, UUIDPrimaryKeyMixin, TimestampMixin)` with `organization_id: uuid.UUID`, `player_uuid: uuid.UUID`, `source_system: str`, `role: OrgRoleName`. `Event` gains `name: str`, `description: str | None`, `organization_id: uuid.UUID`. All consumed by every later task.

- [ ] **Step 1: Write the model file**

```python
# backend/app/models/organization.py
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A store/league/venue that hosts Events. Organizer rights on an
    Event are granted once at the Organization level (`OrganizationMember`)
    rather than per-event, so adding or removing staff doesn't require
    touching every event individually."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(nullable=False)


class OrgRoleName(str, enum.Enum):
    """Roles grantable within an Organization. `JUDGE` has no enforced
    capability difference from `ORGANIZER` yet — reserved for a future
    phase (e.g. penalty issuance) once that feature exists."""

    OWNER = "owner"
    ORGANIZER = "organizer"
    SCOREKEEPER = "scorekeeper"
    JUDGE = "judge"


class OrganizationMember(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Grants one external identity (`player_uuid` + `source_system`,
    NFR4) a role within an Organization."""

    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "player_uuid", "source_system", name="uq_org_member_identity"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    player_uuid: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(nullable=False)
    role: Mapped[OrgRoleName] = mapped_column(
        Enum(
            OrgRoleName,
            name="org_role_name",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
```

- [ ] **Step 2: Add the new fields to `Event`**

Modify `backend/app/models/event.py` — add these three lines after the existing `date` column (keep the existing `date` line and its comment untouched):

```python
    name: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(nullable=True, default=None)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
```

This requires adding imports at the top of the file:
```python
import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
```
(alongside the existing `import datetime as dt` and `sqlalchemy.orm` imports already there).

- [ ] **Step 3: Register the new models in `__init__.py`**

Modify `backend/app/models/__init__.py` to match:

```python
from app.models.base import Base
from app.models.entry import Entry
from app.models.event import Event
from app.models.match import Match, MatchResult
from app.models.organization import Organization, OrganizationMember, OrgRoleName
from app.models.pod import Pod
from app.models.rbac import EventOrganizer, PodRole, PodRoleName
from app.models.round import Round

__all__ = [
    "Base",
    "Entry",
    "Event",
    "EventOrganizer",
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

- [ ] **Step 4: Write the migration**

```python
# backend/alembic/versions/0011_create_organizations_and_add_event_fields.py
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
    conn.execute(
        sa.text("INSERT INTO organizations (id, name, created_at) VALUES (:id, :name, now())"),
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
```

- [ ] **Step 5: Write the model tests**

```python
# backend/tests/integration/test_organization_model.py
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Organization, OrganizationMember, OrgRoleName


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
```

- [ ] **Step 6: Run migration + tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/integration/test_organization_model.py -v`
Expected: 4 passed (this runs against the real Postgres testcontainer via the `migrated_engine`/`db_session` fixtures, which apply every migration up to and including 0011 first).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/organization.py backend/app/models/event.py \
  backend/app/models/__init__.py backend/alembic/versions/0011_create_organizations_and_add_event_fields.py \
  backend/tests/integration/test_organization_model.py
git commit -m "feat(backend): add Organization/OrganizationMember model, Event name/description/organization_id"
```

---

### Task 2: Schemas

**Files:**
- Create: `backend/app/schemas/organization.py`
- Modify: `backend/app/schemas/event.py`

**Interfaces:**
- Consumes: `Organization`, `OrganizationMember`, `OrgRoleName`, `Event` from Task 1.
- Produces: `OrganizationCreate(name: str)`, `OrganizationRead(id, name)`, `OrganizationMemberCreate(player_uuid, source_system, role)`, `OrganizationMemberRead(id, organization_id, player_uuid, source_system, role)`, `EventCreate(date, name, description, organization_id)`, `EventRead(id, date, name, description, organization_id)`, `EventUpdate(date, name, description)`. Consumed by every router task.

- [ ] **Step 1: Write the organization schemas**

```python
# backend/app/schemas/organization.py
import uuid

from pydantic import BaseModel, ConfigDict

from app.models.organization import OrgRoleName


class OrganizationCreate(BaseModel):
    name: str


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class OrganizationMemberCreate(BaseModel):
    player_uuid: uuid.UUID
    source_system: str
    role: OrgRoleName


class OrganizationMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    player_uuid: uuid.UUID
    source_system: str
    role: OrgRoleName
```

- [ ] **Step 2: Update the event schemas**

Replace the full contents of `backend/app/schemas/event.py` with:

```python
import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class EventCreate(BaseModel):
    date: dt.date
    name: str
    description: str | None = None
    organization_id: uuid.UUID


class EventUpdate(BaseModel):
    date: dt.date
    name: str
    description: str | None = None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: dt.date
    name: str
    description: str | None
    organization_id: uuid.UUID
```

Note: `EventUpdate` does not include `organization_id` — this phase has no endpoint for moving an event between organizations, and adding one is out of scope (not in the spec).

- [ ] **Step 3: Verify the app still imports cleanly**

Run: `cd backend && .venv/bin/python -c "from app.main import app"`
Expected: no errors (this catches typos/import mistakes before the next tasks build on these schemas — there's no dedicated test for pure schema classes with no behavior).

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/organization.py backend/app/schemas/event.py
git commit -m "feat(backend): add Organization/OrganizationMember schemas, extend Event schemas"
```

---

### Task 3: Organization CRUD API — create, list

**Files:**
- Create: `backend/app/routers/organizations.py`
- Modify: `backend/app/auth/dependencies.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_organizations_api.py`

**Interfaces:**
- Consumes: `Organization`, `OrganizationMember`, `OrgRoleName` (Task 1); `OrganizationCreate`, `OrganizationRead` (Task 2); `get_current_identity`, `require_organizer_claim` (existing, `app/auth/dependencies.py`).
- Produces: `org_member_role(db: Session, identity: Identity, organization_id: uuid.UUID) -> OrgRoleName | None` in `app/auth/dependencies.py` — consumed by Task 4 (member endpoint auth) and Task 5 (event creation's org-membership check). `router` (prefix `/organizations`) registered in `main.py` — consumed by Task 4 (extends the same router).

- [ ] **Step 1: Add the `org_member_role` helper**

Modify `backend/app/auth/dependencies.py` — add this function after `pod_role_exists` (and add `Organization` handling is not needed here; only `OrganizationMember`/`OrgRoleName` are needed):

```python
def org_member_role(
    db: Session, identity: Identity, organization_id: uuid.UUID
) -> OrgRoleName | None:
    member = (
        db.query(OrganizationMember)
        .filter_by(
            organization_id=organization_id,
            player_uuid=identity.player_uuid,
            source_system=identity.source_system,
        )
        .first()
    )
    return member.role if member is not None else None
```

Add the import at the top of the file, alongside the existing `from app.models.rbac import ...` line:
```python
from app.models.organization import OrganizationMember, OrgRoleName
```

- [ ] **Step 2: Write the failing integration tests**

```python
# backend/tests/integration/test_organizations_api.py
import uuid


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_organizer_claim_creates_organization_and_becomes_owner(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.post(
        "/organizations", json={"name": "Dragon's Den"}, headers=_auth_headers(token)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Dragon's Den"

    list_response = api_client.get("/organizations", headers=_auth_headers(token))
    assert list_response.status_code == 200
    assert [org["id"] for org in list_response.json()] == [body["id"]]


def test_non_organizer_claim_cannot_create_organization(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=[])

    response = api_client.post(
        "/organizations", json={"name": "Dragon's Den"}, headers=_auth_headers(token)
    )

    assert response.status_code == 403


def test_list_organizations_only_shows_orgs_caller_belongs_to(api_client, make_token):
    mine_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    other_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    api_client.post("/organizations", json={"name": "Mine"}, headers=_auth_headers(mine_token))
    api_client.post("/organizations", json={"name": "Other"}, headers=_auth_headers(other_token))

    response = api_client.get("/organizations", headers=_auth_headers(mine_token))

    assert response.status_code == 200
    names = [org["name"] for org in response.json()]
    assert names == ["Mine"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/integration/test_organizations_api.py -v`
Expected: FAIL with 404 (no `/organizations` route registered yet).

- [ ] **Step 4: Write the router**

```python
# backend/app/routers/organizations.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_identity, require_organizer_claim
from app.auth.identity import Identity
from app.db import get_db_session
from app.models.organization import Organization, OrganizationMember, OrgRoleName
from app.schemas.organization import OrganizationCreate, OrganizationRead

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationRead, status_code=201)
def create_organization(
    payload: OrganizationCreate,
    identity: Identity = Depends(require_organizer_claim),
    db: Session = Depends(get_db_session),
) -> Organization:
    org = Organization(name=payload.name)
    db.add(org)
    db.flush()
    db.add(
        OrganizationMember(
            organization_id=org.id,
            player_uuid=identity.player_uuid,
            source_system=identity.source_system,
            role=OrgRoleName.OWNER,
        )
    )
    db.commit()
    db.refresh(org)
    return org


@router.get("", response_model=list[OrganizationRead])
def list_organizations(
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> list[Organization]:
    org_ids = {
        row.organization_id
        for row in db.query(OrganizationMember.organization_id).filter_by(
            player_uuid=identity.player_uuid, source_system=identity.source_system
        )
    }
    if not org_ids:
        return []
    return (
        db.query(Organization)
        .filter(Organization.id.in_(org_ids))
        .order_by(Organization.name, Organization.id)
        .all()
    )
```

- [ ] **Step 5: Register the router**

Modify `backend/app/main.py` — add the import alongside the other router imports and register it alongside the other `app.include_router(...)` calls:

```python
app.include_router(organizations.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/integration/test_organizations_api.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/organizations.py backend/app/auth/dependencies.py \
  backend/app/main.py backend/tests/integration/test_organizations_api.py
git commit -m "feat(backend): add POST/GET /organizations"
```

---

### Task 4: Organization membership API — add member

**Files:**
- Modify: `backend/app/routers/organizations.py`
- Modify: `backend/app/auth/dependencies.py`
- Test: `backend/tests/integration/test_organizations_api.py`

**Interfaces:**
- Consumes: `org_member_role` (Task 3); `OrganizationMemberCreate`, `OrganizationMemberRead` (Task 2).
- Produces: `require_org_owner(organization_id: uuid.UUID, ...) -> Identity` in `app/auth/dependencies.py` — available for future phases, not otherwise consumed within this plan.

- [ ] **Step 1: Add the `require_org_owner` dependency**

Modify `backend/app/auth/dependencies.py` — add this function after `org_member_role` (added in Task 3):

```python
def require_org_owner(
    organization_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Identity:
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="organization not found")
    if org_member_role(db, identity, organization_id) != OrgRoleName.OWNER:
        raise HTTPException(status_code=403, detail="Owner role required for this organization")
    return identity
```

Add `Organization` to the existing `from app.models.organization import OrganizationMember, OrgRoleName` import line (added in Task 3), making it:
```python
from app.models.organization import Organization, OrganizationMember, OrgRoleName
```

- [ ] **Step 2: Write the failing integration tests**

Append to `backend/tests/integration/test_organizations_api.py`:

```python
def _create_org(api_client, token, name="Dragon's Den") -> str:
    return api_client.post(
        "/organizations", json={"name": name}, headers=_auth_headers(token)
    ).json()["id"]


def test_owner_adds_member(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    new_member_uuid = str(uuid.uuid4())

    response = api_client.post(
        f"/organizations/{org_id}/members",
        json={
            "player_uuid": new_member_uuid,
            "source_system": "club-checkin",
            "role": "organizer",
        },
        headers=_auth_headers(owner_token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["player_uuid"] == new_member_uuid
    assert body["role"] == "organizer"


def test_non_owner_cannot_add_member(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.post(
        f"/organizations/{org_id}/members",
        json={
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "role": "organizer",
        },
        headers=_auth_headers(stranger_token),
    )

    assert response.status_code == 403


def test_add_member_to_unknown_organization_returns_404(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.post(
        f"/organizations/{uuid.uuid4()}/members",
        json={
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "role": "organizer",
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/integration/test_organizations_api.py -v -k "member"`
Expected: FAIL with 404 (no `POST /organizations/{id}/members` route yet).

- [ ] **Step 4: Add the member endpoint**

Replace the full contents of `backend/app/routers/organizations.py` with:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_identity, require_organizer_claim, require_org_owner
from app.auth.identity import Identity
from app.db import get_db_session
from app.models.organization import Organization, OrganizationMember, OrgRoleName
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationMemberCreate,
    OrganizationMemberRead,
    OrganizationRead,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationRead, status_code=201)
def create_organization(
    payload: OrganizationCreate,
    identity: Identity = Depends(require_organizer_claim),
    db: Session = Depends(get_db_session),
) -> Organization:
    org = Organization(name=payload.name)
    db.add(org)
    db.flush()
    db.add(
        OrganizationMember(
            organization_id=org.id,
            player_uuid=identity.player_uuid,
            source_system=identity.source_system,
            role=OrgRoleName.OWNER,
        )
    )
    db.commit()
    db.refresh(org)
    return org


@router.get("", response_model=list[OrganizationRead])
def list_organizations(
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> list[Organization]:
    org_ids = {
        row.organization_id
        for row in db.query(OrganizationMember.organization_id).filter_by(
            player_uuid=identity.player_uuid, source_system=identity.source_system
        )
    }
    if not org_ids:
        return []
    return (
        db.query(Organization)
        .filter(Organization.id.in_(org_ids))
        .order_by(Organization.name, Organization.id)
        .all()
    )


@router.post("/{organization_id}/members", response_model=OrganizationMemberRead, status_code=201)
def add_organization_member(
    organization_id: uuid.UUID,
    payload: OrganizationMemberCreate,
    identity: Identity = Depends(require_org_owner),
    db: Session = Depends(get_db_session),
) -> OrganizationMember:
    member = OrganizationMember(
        organization_id=organization_id,
        player_uuid=payload.player_uuid,
        source_system=payload.source_system,
        role=payload.role,
    )
    db.add(member)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="this identity already has a role on this organization"
        ) from None
    db.refresh(member)
    return member
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/integration/test_organizations_api.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/organizations.py backend/app/auth/dependencies.py \
  backend/tests/integration/test_organizations_api.py
git commit -m "feat(backend): add POST /organizations/{id}/members"
```

---

### Task 5: Event creation requires an Organization

**Files:**
- Modify: `backend/app/routers/events.py`
- Test: `backend/tests/integration/test_events_api.py`

**Interfaces:**
- Consumes: `org_member_role`, `OrgRoleName` (Tasks 1/3); `EventCreate`/`EventRead` (Task 2, already includes `organization_id`/`name`/`description`).

- [ ] **Step 1: Update the existing tests to pass the new required fields**

`test_events_api.py` currently has 10 call sites posting `{"date": "..."}"` — every one needs an organization first. Replace the full contents of `backend/tests/integration/test_events_api.py` with:

```python
import uuid


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_org(api_client, token, name="Test Org") -> str:
    return api_client.post(
        "/organizations", json={"name": name}, headers=_auth_headers(token)
    ).json()["id"]


def test_organizer_claim_creates_event_and_becomes_its_organizer(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, token)

    response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["date"] == "2026-09-01"
    assert body["name"] == "Friday Standard"
    assert body["organization_id"] == org_id
    assert body["description"] is None

    get_response = api_client.get(f"/events/{body['id']}", headers=_auth_headers(token))
    assert get_response.status_code == 200


def test_event_creation_accepts_optional_description(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, token)

    response = api_client.post(
        "/events",
        json={
            "date": "2026-09-01",
            "name": "Friday Standard",
            "description": "Weekly league night",
            "organization_id": org_id,
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["description"] == "Weekly league night"


def test_non_organizer_claim_cannot_create_event(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=[])

    response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": str(uuid.uuid4())},
        headers=_auth_headers(token),
    )

    assert response.status_code == 403


def test_caller_without_org_membership_cannot_create_event(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(stranger_token),
    )

    assert response.status_code == 403


def test_org_organizer_role_can_create_event(api_client, make_token):
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

    response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(staff_token),
    )

    assert response.status_code == 201


def test_unrelated_identity_cannot_read_event(api_client, make_token):
    creator_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, creator_token)
    create_response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(creator_token),
    )
    event_id = create_response.json()["id"]

    other_token = make_token(player_uuid=uuid.uuid4(), roles=[])
    response = api_client.get(f"/events/{event_id}", headers=_auth_headers(other_token))

    assert response.status_code == 403


def test_organizer_can_update_and_delete_own_event(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, token)
    event_id = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(token),
    ).json()["id"]

    patch_response = api_client.patch(
        f"/events/{event_id}",
        json={"date": "2026-09-02", "name": "Friday Standard (Moved)"},
        headers=_auth_headers(token),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["date"] == "2026-09-02"
    assert patch_response.json()["name"] == "Friday Standard (Moved)"

    delete_response = api_client.delete(f"/events/{event_id}", headers=_auth_headers(token))
    assert delete_response.status_code == 204

    get_response = api_client.get(f"/events/{event_id}", headers=_auth_headers(token))
    assert get_response.status_code == 404


def test_list_events_only_shows_visible_events(api_client, make_token):
    mine_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    mine_org_id = _create_org(api_client, mine_token, name="Mine Org")
    other_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    other_org_id = _create_org(api_client, other_token, name="Other Org")

    api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Mine", "organization_id": mine_org_id},
        headers=_auth_headers(mine_token),
    )
    api_client.post(
        "/events",
        json={"date": "2026-09-05", "name": "Other", "organization_id": other_org_id},
        headers=_auth_headers(other_token),
    )

    response = api_client.get("/events", headers=_auth_headers(mine_token))

    assert response.status_code == 200
    dates = [event["date"] for event in response.json()]
    assert dates == ["2026-09-01"]
```

Note: `make_token`'s fixture wrapper (`backend/tests/integration/conftest.py`) already accepts `source_system` as a kwarg (default `"club-checkin"`) — `test_org_organizer_role_can_create_event` above passes it explicitly to match the identity that was granted org membership. No fixture changes needed.

- [ ] **Step 2: Run tests to verify the new/changed ones fail**

Run: `cd backend && .venv/bin/pytest tests/integration/test_events_api.py -v`
Expected: FAIL — `test_event_creation_accepts_optional_description`, `test_caller_without_org_membership_cannot_create_event`, and `test_org_organizer_role_can_create_event` fail (route doesn't check org membership yet); others fail with 422 (route doesn't accept `name`/`organization_id` yet).

- [ ] **Step 3: Update the router**

Replace `create_event` in `backend/app/routers/events.py`:

```python
def create_event(
    payload: EventCreate,
    identity: Identity = Depends(require_organizer_claim),
    db: Session = Depends(get_db_session),
) -> Event:
    role = org_member_role(db, identity, payload.organization_id)
    if role not in (OrgRoleName.OWNER, OrgRoleName.ORGANIZER):
        raise HTTPException(
            status_code=403, detail="Owner or Organizer role required for this organization"
        )

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

Add these imports at the top of `events.py`, alongside the existing ones:
```python
from app.auth.dependencies import org_member_role
from app.models.organization import OrgRoleName
```

Also update `update_event` to set the new fields (its payload, `EventUpdate`, already has `name`/`description` from Task 2):

```python
def update_event(
    event_id: uuid.UUID,
    payload: EventUpdate,
    identity: Identity = Depends(require_event_organizer),
    db: Session = Depends(get_db_session),
) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    event.date = payload.date
    event.name = payload.name
    event.description = payload.description
    db.commit()
    db.refresh(event)
    return event
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/integration/test_events_api.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/events.py backend/tests/integration/test_events_api.py
git commit -m "feat(backend): require Organization membership to create an Event"
```

---

### Task 6: Fix the rest of the integration suite

The change in Task 5 breaks every other integration test file that creates an event via a local helper without an `organization_id`/`name` — this task is purely mechanical: give each file's helper its own organization first, then pass `organization_id`/`name` through.

**Files:**
- Modify: `backend/tests/integration/test_entries_api.py`
- Modify: `backend/tests/integration/test_matches_api.py`
- Modify: `backend/tests/integration/test_pod_roles_api.py`
- Modify: `backend/tests/integration/test_report_flow_api.py`
- Modify: `backend/tests/integration/test_pods_api.py`
- Modify: `backend/tests/integration/test_pairings_flow_api.py`
- Modify: `backend/tests/integration/test_setup_flow_api.py`
- Modify: `backend/tests/integration/test_rounds_api.py`

**Interfaces:**
- Consumes: `POST /organizations` (Task 3), `POST /events` with `name`/`organization_id` (Task 5).

- [ ] **Step 1: Run the full suite to confirm the exact failures**

Run: `cd backend && .venv/bin/pytest -q`
Expected: FAIL — every test in the 8 files above fails with 422 (missing `name`/`organization_id` in the `/events` payload).

- [ ] **Step 2: Fix `test_entries_api.py`**

It has a `_create_pod(api_client, token)` helper (line ~11) plus two extra inline `POST /events` calls in `test_pod_creation_rejects_unknown_game_slug_with_422_not_500` and `test_entry_creation_rejects_pod_with_unregistered_game_slug_with_422_not_500`. Change the helper to:

```python
def _create_pod(api_client, token) -> str:
    org_id = api_client.post(
        "/organizations", json={"name": "Test Org"}, headers=_auth_headers(token)
    ).json()["id"]
    event_id = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Test Event", "organization_id": org_id},
        headers=_auth_headers(token),
    ).json()["id"]
    return api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    ).json()["id"]
```

For the two inline `POST /events` calls in the two `_with_422_not_500` tests, apply the same pattern inline: create an org first (`org_id = api_client.post("/organizations", json={"name": "Test Org"}, headers=_auth_headers(token)).json()["id"]`), then add `"name": "Test Event", "organization_id": org_id` to that call's JSON payload.

- [ ] **Step 3: Fix the remaining 7 files' `_create_pod`/`_create_event` helpers**

Every other file's helper follows the identical shape — a `_create_pod(api_client, token) -> str` (or, in `test_pods_api.py`, `_create_event(api_client, token) -> str`) that starts with a bare `POST /events`. Apply the exact same transformation as Step 2 to each: insert an org-creation call before the events call, and add `"name": "Test Event", "organization_id": org_id` to the events payload. This applies to:
- `test_matches_api.py`'s `_create_pod`
- `test_pod_roles_api.py`'s `_create_pod`
- `test_report_flow_api.py`'s `_create_pod`
- `test_pairings_flow_api.py`'s `_create_pod`
- `test_rounds_api.py`'s `_create_pod` (note its signature is `_create_pod(api_client, token, format_slug="swiss")` — keep the `format_slug` parameter untouched, only change the body)
- `test_pods_api.py`'s `_create_event` (this one returns an event id directly, not a pod id — same org-creation insertion, just don't add the `/pods` call since this helper doesn't have one)

- [ ] **Step 4: Fix `test_setup_flow_api.py`**

This file has no helper — a single test (`test_organizer_setup_flow_create_event_pod_entries`) inlines its own `POST /events` call. Add an org-creation call immediately before it and extend the payload the same way.

- [ ] **Step 5: Run the full suite to verify everything passes**

Run: `cd backend && .venv/bin/pytest -q`
Expected: all tests pass (should be around 220+, matching the pre-existing 214 plus this plan's new tests from Tasks 1/3/4/5).

- [ ] **Step 6: Commit**

```bash
git add backend/tests/integration/test_entries_api.py backend/tests/integration/test_matches_api.py \
  backend/tests/integration/test_pod_roles_api.py backend/tests/integration/test_report_flow_api.py \
  backend/tests/integration/test_pods_api.py backend/tests/integration/test_pairings_flow_api.py \
  backend/tests/integration/test_setup_flow_api.py backend/tests/integration/test_rounds_api.py
git commit -m "test(backend): update existing integration suite for required Event.organization_id"
```

---

### Task 7: Frontend API client

**Files:**
- Create: `frontend/src/api/organizations.ts`
- Test: `frontend/src/api/organizations.test.ts`
- Modify: `frontend/src/api/events.ts`
- Modify: `frontend/src/api/events.test.ts`

**Interfaces:**
- Produces: `OrganizationRead { id: string; name: string }`, `listOrganizations(apiFetch): Promise<OrganizationRead[]>`, `createOrganization(apiFetch, name: string): Promise<OrganizationRead>` — consumed by Task 8. `EventRead` gains `name`/`description`/`organization_id`; `createEvent`'s signature changes — consumed by Task 8.

- [ ] **Step 1: Write the organizations API client**

```typescript
// frontend/src/api/organizations.ts
import { apiRequest, jsonInit, type ApiFetch } from "./request";

export interface OrganizationRead {
  id: string;
  name: string;
}

export function listOrganizations(apiFetch: ApiFetch): Promise<OrganizationRead[]> {
  return apiRequest(apiFetch, "/organizations");
}

export function createOrganization(apiFetch: ApiFetch, name: string): Promise<OrganizationRead> {
  return apiRequest(apiFetch, "/organizations", jsonInit("POST", { name }));
}
```

- [ ] **Step 2: Write the test**

`frontend/src/api/pods.test.ts` is this codebase's established pattern for API-client-only tests: a hand-rolled `vi.fn().mockResolvedValue({ ok, status, json })` standing in for `apiFetch`, asserting both the parsed return value and the exact `apiFetch` call arguments — no MSW involved at this layer (MSW is reserved for component-level tests via `renderWithProviders`). Mirror it exactly:

```typescript
// frontend/src/api/organizations.test.ts
import { describe, expect, it, vi } from "vitest";
import { createOrganization, listOrganizations } from "./organizations";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

describe("organizations api", () => {
  it("listOrganizations GETs /organizations", async () => {
    const apiFetch = fetchReturning([{ id: "org-1", name: "Dragon's Den" }]);

    const orgs = await listOrganizations(apiFetch);

    expect(orgs).toEqual([{ id: "org-1", name: "Dragon's Den" }]);
    expect(apiFetch).toHaveBeenCalledWith("/organizations", undefined);
  });

  it("createOrganization POSTs the name", async () => {
    const apiFetch = fetchReturning({ id: "org-2", name: "New Org" }, 201);

    await createOrganization(apiFetch, "New Org");

    expect(apiFetch).toHaveBeenCalledWith("/organizations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "New Org" }),
    });
  });
});
```

- [ ] **Step 3: Run test to verify it passes**

Run: `cd frontend && npm run test -- --run src/api/organizations.test.ts`
Expected: 2 passed (this is written after the implementation in Step 1 — matching how `pods.ts`/`pods.test.ts` are structured in this codebase, plain request/response plumbing verified after the fact rather than RED-GREEN, since there's no behavior to drive out before the client exists).

- [ ] **Step 4: Update the events API client**

Replace the full contents of `frontend/src/api/events.ts`:

```typescript
import { apiRequest, jsonInit, type ApiFetch } from "./request";

export interface EventRead {
  id: string;
  date: string;
  name: string;
  description: string | null;
  organization_id: string;
}

export function listEvents(apiFetch: ApiFetch): Promise<EventRead[]> {
  return apiRequest(apiFetch, "/events");
}

export function getEvent(apiFetch: ApiFetch, eventId: string): Promise<EventRead> {
  return apiRequest(apiFetch, `/events/${eventId}`);
}

export function createEvent(
  apiFetch: ApiFetch,
  date: string,
  name: string,
  organizationId: string,
  description?: string,
): Promise<EventRead> {
  return apiRequest(
    apiFetch,
    "/events",
    jsonInit("POST", { date, name, description, organization_id: organizationId }),
  );
}
```

- [ ] **Step 5: Fix `events.test.ts`'s own assertions**

`frontend/src/api/events.test.ts` breaks with the new `createEvent` signature and `EventRead` shape. Replace its full contents:

```typescript
import { describe, expect, it, vi } from "vitest";
import { createEvent, getEvent, listEvents } from "./events";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

const EVENT_FIXTURE = {
  id: "1",
  date: "2026-08-01",
  name: "Friday Standard",
  description: null,
  organization_id: "org-1",
};

describe("events api", () => {
  it("listEvents GETs /events", async () => {
    const apiFetch = fetchReturning([EVENT_FIXTURE]);

    expect(await listEvents(apiFetch)).toEqual([EVENT_FIXTURE]);
    expect(apiFetch).toHaveBeenCalledWith("/events", undefined);
  });

  it("getEvent GETs /events/:id", async () => {
    const apiFetch = fetchReturning(EVENT_FIXTURE);

    expect(await getEvent(apiFetch, "1")).toEqual(EVENT_FIXTURE);
    expect(apiFetch).toHaveBeenCalledWith("/events/1", undefined);
  });

  it("createEvent POSTs date, name, organization_id, and optional description", async () => {
    const apiFetch = fetchReturning(EVENT_FIXTURE, 201);

    await createEvent(apiFetch, "2026-08-01", "Friday Standard", "org-1");

    expect(apiFetch).toHaveBeenCalledWith("/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        date: "2026-08-01",
        name: "Friday Standard",
        description: undefined,
        organization_id: "org-1",
      }),
    });
  });

  it("createEvent includes description when provided", async () => {
    const apiFetch = fetchReturning(EVENT_FIXTURE, 201);

    await createEvent(apiFetch, "2026-08-01", "Friday Standard", "org-1", "Weekly league night");

    expect(apiFetch).toHaveBeenCalledWith(
      "/events",
      expect.objectContaining({
        body: JSON.stringify({
          date: "2026-08-01",
          name: "Friday Standard",
          description: "Weekly league night",
          organization_id: "org-1",
        }),
      }),
    );
  });
});
```

- [ ] **Step 6: Update any other existing fixtures shaped like `EventRead`**

Grep for other test fixtures that construct an `EventRead`-shaped object (`{ id: ..., date: ... }` without `name`) — likely in `NewEvent.test.tsx`, `EventList.test.tsx`, `EventDetail.test.tsx`, and any MSW handler returning event JSON elsewhere. Add `name`, `description: null`, `organization_id` to each so they still typecheck as valid `EventRead` objects (`tsc --noEmit` will list every one that's missing a field — use that as the checklist).

- [ ] **Step 7: Run typecheck and existing tests**

Run: `cd frontend && npx tsc --noEmit && npm run test -- --run`
Expected: `tsc` clean; existing event-related tests may still fail here since `NewEvent.tsx` itself isn't updated yet (Task 8) — that's expected at this point, note which failures are pre-existing-and-expected vs. new/unexpected before moving on.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/organizations.ts frontend/src/api/organizations.test.ts \
  frontend/src/api/events.ts frontend/src/api/events.test.ts
git commit -m "feat(frontend): add organizations API client, extend events API client"
```

(Include any other fixture files touched in Step 6 in this same commit.)

---

### Task 8: Frontend — NewEvent stopgap, display event name

**Files:**
- Modify: `frontend/src/routes/NewEvent.tsx`
- Modify: `frontend/src/routes/NewEvent.test.tsx`
- Modify: `frontend/src/routes/EventList.tsx`
- Modify: `frontend/src/routes/EventList.test.tsx`
- Modify: `frontend/src/routes/EventDetail.tsx`
- Modify: `frontend/src/routes/EventDetail.test.tsx`

**Interfaces:**
- Consumes: `listOrganizations`, `createOrganization` (Task 7); `createEvent`'s new signature (Task 7).

- [ ] **Step 1: Write the failing tests**

Replace the full contents of `frontend/src/routes/NewEvent.test.tsx`:

```typescript
import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { NewEvent } from "./NewEvent";

describe("NewEvent", () => {
  beforeEach(() => localStorage.clear());

  it("creates an event under an existing organization and navigates to its detail page", async () => {
    server.use(
      http.get("/organizations", () =>
        HttpResponse.json([{ id: "org-1", name: "Dragon's Den" }]),
      ),
      http.post("/events", async ({ request }) => {
        const body = (await request.json()) as { date: string; name: string; organization_id: string };
        return HttpResponse.json(
          { id: "new-1", date: body.date, name: body.name, description: null, organization_id: body.organization_id },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(<NewEvent />, { path: "/events/new" });

    await screen.findByText("Dragon's Den");
    fireEvent.change(screen.getByLabelText("Event name"), { target: { value: "Friday Standard" } });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-08-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Event" }));

    expect(await screen.findByTestId("navigated-to")).toHaveTextContent("/events/new-1");
  });

  it("offers inline organization creation when the caller belongs to no organizations", async () => {
    server.use(
      http.get("/organizations", () => HttpResponse.json([])),
      http.post("/organizations", async ({ request }) => {
        const body = (await request.json()) as { name: string };
        return HttpResponse.json({ id: "org-new", name: body.name }, { status: 201 });
      }),
      http.post("/events", async ({ request }) => {
        const body = (await request.json()) as { date: string; name: string; organization_id: string };
        return HttpResponse.json(
          { id: "new-2", date: body.date, name: body.name, description: null, organization_id: body.organization_id },
          { status: 201 },
        );
      }),
    );

    renderWithProviders(<NewEvent />, { path: "/events/new" });

    await screen.findByLabelText("New organization name");
    fireEvent.change(screen.getByLabelText("New organization name"), { target: { value: "New Store" } });
    fireEvent.click(screen.getByRole("button", { name: "Create organization" }));

    await screen.findByText("New Store");
    fireEvent.change(screen.getByLabelText("Event name"), { target: { value: "Friday Standard" } });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-08-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Event" }));

    expect(await screen.findByTestId("navigated-to")).toHaveTextContent("/events/new-2");
  });

  it("surfaces a validation error from the backend", async () => {
    server.use(
      http.get("/organizations", () =>
        HttpResponse.json([{ id: "org-1", name: "Dragon's Den" }]),
      ),
      http.post("/events", () => HttpResponse.json({ detail: "date is required" }, { status: 422 })),
    );

    renderWithProviders(<NewEvent />, { path: "/events/new" });

    await screen.findByText("Dragon's Den");
    fireEvent.change(screen.getByLabelText("Event name"), { target: { value: "Friday Standard" } });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-08-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Event" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("date is required");
  });

  it("redirects a non-Organizer persona away from the form", async () => {
    renderWithProviders(<NewEvent />, { path: "/events/new", personaLabel: "Player" });

    expect(await screen.findByTestId("navigated-to")).toHaveTextContent("/");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test -- --run src/routes/NewEvent.test.tsx`
Expected: FAIL — the current `NewEvent.tsx` has no name field, no org picker, and `createEvent`'s call signature no longer matches.

- [ ] **Step 3: Rewrite `NewEvent.tsx`**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router";
import { createEvent } from "../api/events";
import { createOrganization, listOrganizations } from "../api/organizations";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

export function NewEvent() {
  const { apiFetch, currentPersona } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [date, setDate] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [newOrgName, setNewOrgName] = useState("");

  const organizationsQuery = useQuery({
    queryKey: ["organizations"],
    queryFn: () => listOrganizations(apiFetch),
  });

  const createOrgMutation = useMutation({
    mutationFn: () => createOrganization(apiFetch, newOrgName),
    onSuccess: (org) => {
      queryClient.invalidateQueries({ queryKey: ["organizations"] });
      setOrganizationId(org.id);
      setNewOrgName("");
    },
  });

  const mutation = useMutation({
    mutationFn: () => createEvent(apiFetch, date, name, organizationId, description || undefined),
    onSuccess: (event) => {
      queryClient.invalidateQueries({ queryKey: ["events"] });
      navigate(`/events/${event.id}`);
    },
  });

  if (currentPersona.role !== "organizer") {
    return <Navigate to="/" replace />;
  }

  const organizations = organizationsQuery.data ?? [];

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        mutation.mutate();
      }}
    >
      <h2 className="mb-4 text-lg font-semibold">New Event</h2>
      <ErrorBanner error={mutation.error ?? organizationsQuery.error ?? createOrgMutation.error} />

      <label className="block text-sm">
        Event name
        <input
          type="text"
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="mt-1 block rounded border border-gray-300 px-2 py-1"
        />
      </label>

      <label className="mt-2 block text-sm">
        Description
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          className="mt-1 block rounded border border-gray-300 px-2 py-1"
        />
      </label>

      <label className="mt-2 block text-sm">
        Date
        <input
          type="date"
          required
          value={date}
          onChange={(event) => setDate(event.target.value)}
          className="mt-1 block rounded border border-gray-300 px-2 py-1"
        />
      </label>

      {organizations.length > 0 ? (
        <label className="mt-2 block text-sm">
          Organization
          <select
            required
            value={organizationId}
            onChange={(event) => setOrganizationId(event.target.value)}
            className="mt-1 block rounded border border-gray-300 px-2 py-1"
          >
            <option value="" disabled>
              Select an organization
            </option>
            {organizations.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </select>
        </label>
      ) : (
        organizationsQuery.isSuccess && (
          <div className="mt-2">
            <label className="block text-sm">
              New organization name
              <input
                type="text"
                value={newOrgName}
                onChange={(event) => setNewOrgName(event.target.value)}
                className="mt-1 block rounded border border-gray-300 px-2 py-1"
              />
            </label>
            <button
              type="button"
              disabled={createOrgMutation.isPending || newOrgName.trim() === ""}
              onClick={() => createOrgMutation.mutate()}
              className="mt-2 rounded border border-gray-300 px-3 py-1.5 text-sm"
            >
              Create organization
            </button>
          </div>
        )
      )}

      <button
        type="submit"
        disabled={mutation.isPending || organizationId === ""}
        className="mt-4 rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
      >
        Create Event
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm run test -- --run src/routes/NewEvent.test.tsx`
Expected: 4 passed.

- [ ] **Step 5: Display the event name in `EventList.tsx` and `EventDetail.tsx`**

In `frontend/src/routes/EventList.tsx`, change the link text from `{event.date}` to `{event.name}`:
```typescript
              <Link to={`/events/${event.id}`} className="text-blue-700 hover:underline">
                {event.name}
              </Link>
```

In `frontend/src/routes/EventDetail.tsx`, change the heading from showing only the date to showing the name (keep the date visible too):
```typescript
      <h2 className="mb-4 text-lg font-semibold">
        {eventQuery.data ? eventQuery.data.name : "…"}
      </h2>
      {eventQuery.data && <p className="mb-4 text-sm text-gray-600">{eventQuery.data.date}</p>}
```

`EventList.test.tsx`'s first test asserts on the link's accessible name, which changes from the date text to the name text — replace its fixture and assertions:

```typescript
  it("renders events as links to their detail page", async () => {
    server.use(
      http.get("/events", () =>
        HttpResponse.json([
          { id: "1", date: "2026-08-01", name: "Friday Standard", description: null, organization_id: "org-1" },
          { id: "2", date: "2026-09-01", name: "Regional Qualifier", description: null, organization_id: "org-1" },
        ]),
      ),
    );

    renderWithProviders(<EventList />);

    expect(await screen.findByRole("link", { name: "Friday Standard" })).toHaveAttribute("href", "/events/1");
    expect(screen.getByRole("link", { name: "Regional Qualifier" })).toHaveAttribute("href", "/events/2");
    // Default persona (personas[0] in public/config.json) is Organizer.
    expect(screen.getByRole("link", { name: "New Event" })).toHaveAttribute("href", "/events/new");
  });
```

`EventDetail.test.tsx`'s shared `EVENT` constant (used by every test in the file) just needs the new fields added — no assertion in that file checks the heading text directly:

```typescript
const EVENT = { id: "event-1", date: "2026-08-01", name: "Friday Standard", description: null, organization_id: "org-1" };
```

- [ ] **Step 6: Run the full frontend suite**

Run: `cd frontend && npm run test -- --run && npx tsc --noEmit`
Expected: all tests pass, `tsc` clean.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/routes/NewEvent.tsx frontend/src/routes/NewEvent.test.tsx \
  frontend/src/routes/EventList.tsx frontend/src/routes/EventList.test.tsx \
  frontend/src/routes/EventDetail.tsx frontend/src/routes/EventDetail.test.tsx
git commit -m "feat(frontend): NewEvent org picker/create-inline, name field; display event name"
```
