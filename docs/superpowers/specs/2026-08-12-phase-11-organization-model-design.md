# Phase 11 — Organization Data Model (Design)

Date: 2026-08-12
Status: Approved (brainstorming), pending plan/execution
Requirement: new FR (to be added to `REQUIREMENTS.md`), MVP2

Related: this is the first of a three-phase sub-project inserted into MVP2's
Build Order ahead of the Pokémon phases (previously Phase 11 GameModule,
12 tiebreak, 13 OIDC, 14 verification — all shift by three slots once this
sub-project's phases are numbered in `REQUIREMENTS.md`):

1. **This phase** — `Organization`/`OrganizationMember` data model,
   `Event.name`/`description`/`organization_id`, minimal org CRUD API, and
   a minimal frontend stopgap so event creation doesn't break.
2. **RBAC cutover** (future phase) — replace `EventOrganizer`-based
   authorization checks across every operational router (pods, entries,
   rounds, matches) with org-membership resolution; retire
   `EventOrganizer`.
3. **Frontend org management** (future phase) — full org
   creation/membership/role management UI.

## 1. Scope

Today `Event` has only a `date` (FR7, deliberate MVP1 scope — "in-person
only for v1") and there is no `Organization` entity anywhere in the schema.
`EventOrganizer` is a pure per-event RBAC grant row
(`event_id, player_uuid, source_system`) with no display name and no
identity that persists across events — adding or removing a staffer means
touching every event individually, and there is no "hosted by X" concept
to show players.

**In scope for this phase:**
- `Organization` model (name only).
- `OrganizationMember` model: identity (`player_uuid`, `source_system`,
  matching the existing external-identity pattern, NFR4) + `role`
  (`OWNER`, `ORGANIZER`, `SCOREKEEPER`, `JUDGE`).
- `Event` gains `name` (required), `description` (optional),
  `organization_id` (required FK to `organizations.id`).
- Minimal operational API: create an organization (creator becomes
  `OWNER`), list organizations you belong to, add a member (`OWNER`-only).
- `POST /events` requires `organization_id`/`name`; caller must be an
  `OWNER` or `ORGANIZER` member of that org (checked only at this one
  endpoint — not a repo-wide cutover). `EventOrganizer` is still
  dual-written on event creation so every other existing router (pods,
  entries, rounds, matches — all of which still call
  `event_organizer_exists`) keeps working completely unchanged.
- Migration: new tables, plus `events.name`/`organization_id` backfilled
  (placeholder org + placeholder name for any pre-existing rows) then
  altered to `NOT NULL` in the same migration, mirroring migration 0009's
  backfill pattern.
- Minimal frontend stopgap on `NewEvent.tsx`: required name field,
  optional description field, an organization picker that falls back to
  an inline "create organization" mini-form when the caller belongs to no
  organizations yet. No membership/role management UI — that's phase 3.

**Out of scope (explicitly deferred to future phases):**
- Replacing `EventOrganizer`-based authorization anywhere except the one
  new check on `POST /events` (phase 2).
- Any UI for managing org membership, editing roles, removing members, or
  editing/deleting an organization (phase 3).
- Any distinct capability for the `JUDGE` role — it exists in the schema
  and is returned/settable everywhere a role appears, but on
  organization-membership endpoints (`POST /organizations/{id}/members`,
  `GET /organizations`) it has zero enforced difference from `ORGANIZER`
  right now. This does *not* extend to event creation: `POST /events`
  requires `OWNER` or `ORGANIZER` specifically (see §3), so `JUDGE` (and
  `SCOREKEEPER`) members are rejected with 403 there, same as any other
  non-qualifying role. A future phase gives `JUDGE` something to do (e.g.
  penalty issuance) once that feature exists.
- Any org-level branding beyond a name (no address, contact info, logo,
  etc.) — YAGNI until a concrete need appears.

## 2. Data model

```python
# backend/app/models/organization.py
class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(nullable=False)


class OrgRoleName(str, enum.Enum):
    OWNER = "owner"
    ORGANIZER = "organizer"
    SCOREKEEPER = "scorekeeper"
    JUDGE = "judge"


class OrganizationMember(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "player_uuid", "source_system",
            name="uq_org_member_identity",
        ),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    player_uuid: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_system: Mapped[str] = mapped_column(nullable=False)
    role: Mapped[OrgRoleName] = mapped_column(Enum(OrgRoleName), nullable=False)
```

`backend/app/models/event.py`'s `Event` gains:
```python
name: Mapped[str] = mapped_column(nullable=False)
description: Mapped[str | None] = mapped_column(nullable=True, default=None)
organization_id: Mapped[uuid.UUID] = mapped_column(
    PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
)
```

`EventRead`/`EventCreate` schemas gain the matching fields.
`OrganizationRead`/`OrganizationCreate` and
`OrganizationMemberRead`/`OrganizationMemberCreate` schemas are new,
following the existing `*Read`/`*Create` split used by every other model
in `backend/app/schemas/`.

## 3. API

```
POST /organizations {name}
  Auth: require_organizer_claim (same JWT-level bar as today's event
  creation — no org-membership check possible yet, since the org doesn't
  exist until this call succeeds).
  Creates Organization, then an OrganizationMember row for the caller
  with role=OWNER. Returns OrganizationRead.

GET /organizations
  Auth: get_current_identity.
  Returns organizations where the caller has an OrganizationMember row
  (any role).

POST /organizations/{id}/members {player_uuid, source_system, role}
  Auth: get_current_identity; caller must have an OrganizationMember row
  on {id} with role=OWNER, else 403. 404 if the organization doesn't
  exist.
  Creates the OrganizationMember row. Returns OrganizationMemberRead.
```

`POST /events` payload becomes
`{date, name, description?, organization_id}`. Auth:
`require_organizer_claim`, plus a new check — caller must have an
`OrganizationMember` row on `organization_id` with role `OWNER` or
`ORGANIZER`, else 403. On success, the endpoint still creates the
`EventOrganizer` row exactly as it does today (dual-write), so
`pods.py`/`entries.py`/`rounds.py`/`matches.py` — none of which are
touched in this phase — continue resolving authorization exactly as
before.

## 4. Migration

One Alembic migration:
1. Create `organizations` (id, name, timestamps).
2. Create `organization_members` (id, organization_id FK, player_uuid,
   source_system, role, timestamps, unique constraint on
   `(organization_id, player_uuid, source_system)`).
3. Add `events.name` (nullable), `events.description` (nullable),
   `events.organization_id` (nullable FK) as three separate `ADD COLUMN`
   steps.
4. Data migration: insert one placeholder `Organization` row
   (`name="Unassigned"`); for every existing `Event` row with a NULL
   `organization_id`, set it to that placeholder's id and set `name` to a
   placeholder value (`"Untitled Event"`) if NULL.
5. Alter `events.name` and `events.organization_id` to `NOT NULL`.

No membership is created for the placeholder organization — it exists
only so pre-existing `Event` rows have a valid FK target. Those events'
`EventOrganizer` grants (from before this migration) are untouched and
keep working exactly as they do today, since this phase doesn't change
any authorization path except the new one on `POST /events`.

## 5. Frontend (stopgap only — full org UI is phase 3)

`frontend/src/routes/NewEvent.tsx` gains:
- A required "Event name" text input.
- An optional "Description" textarea.
- An organization picker: fetches `GET /organizations`. If the list is
  non-empty, renders a `<select>` of org names. If empty, renders an
  inline "Create organization" mini-form (a single name input + button)
  that calls `POST /organizations` and then uses the newly-created org
  for the event being created.

No UI is added for listing an org's members, changing roles, or editing
an organization's name — those all wait for phase 3.

## 6. Testing

- **Unit/Integration (backend)**: `Organization`/`OrganizationMember`
  model round-trip tests; `POST /organizations` (creator becomes
  `OWNER`); `POST /organizations/{id}/members` (`OWNER`-only, 403 for
  `ORGANIZER`/`SCOREKEEPER`/`JUDGE` callers and for non-members, 404 for
  an unknown org id); `POST /events` requires `organization_id`/`name`
  (422 if missing), 403 if the caller isn't `OWNER`/`ORGANIZER` on that
  org, `EventOrganizer` still created on success (existing
  `event_organizer_exists`-based tests on other routers keep passing
  unmodified, proving the dual-write didn't break anything downstream).
  Migration backfill verified against a real Postgres testcontainer:
  seed a pre-migration `Event` row with the old schema, run the new
  migration, assert it lands in the placeholder org with a placeholder
  name and both columns are `NOT NULL` afterward.
- **Frontend**: `NewEvent.tsx` — org-picker rendering when
  `GET /organizations` returns entries vs. the inline create-form when it
  returns empty; required-field validation on name; the full
  create-org-then-create-event flow via MSW.

## 7. Open questions

None outstanding — all four design sections were reviewed and approved
section-by-section with the owner during brainstorming (2026-08-12).
