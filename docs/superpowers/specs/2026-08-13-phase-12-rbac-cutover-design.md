# Phase 12 — RBAC Cutover to Org Membership (Design)

Date: 2026-08-13
Status: Approved (brainstorming), pending plan/execution
Requirement: FR32, MVP2
Related: second of the 3-phase Organization/RBAC sub-project. Depends on
Phase 11 (`Organization`/`OrganizationMember` data model, PR #71, merged).
Issue #69 (this phase). Issue #72 items 1 and 2 (deferred from Phase 11's
`/review`) are folded in — see §6.

## 1. Scope

Today, organizer authorization across every operational router (events,
pods, entries, rounds, matches, pod_roles) still resolves through the
per-event `EventOrganizer` grant table, even though Phase 11 introduced
`Organization`/`OrganizationMember` as the intended durable grant. Only
`POST /events` checks org membership; everything else still calls
`event_organizer_exists`/`require_event_organizer`/`require_pod_organizer`,
which query `EventOrganizer`.

This leaves two known gaps (flagged in PR #71's review, tracked as issue
#72 items 1-2):
1. An org OWNER cannot see/operate on events an ORGANIZER on the same org
   created, because `EventOrganizer` only ever has a row for the event's
   creator, and `visible_event_ids` doesn't consult org membership.
2. There's no way to revoke an `OrganizationMember` grant — a mistaken
   OWNER grant is permanent until Phase 13's management UI ships.

**In scope for this phase:**
- Every router currently calling `event_organizer_exists` /
  `require_event_organizer` / `require_pod_organizer` (directly or via
  `pod_access_allowed`/`pod_staff_allowed`) resolves via
  `OrganizationMember` instead. "Organizer" = org role `OWNER` or
  `ORGANIZER` on the event's `organization_id` — equivalent to the old
  `EventOrganizer` grant. `SCOREKEEPER`/`JUDGE` org roles confer nothing
  extra at pod/entry/round/match level; `PodRole` (the existing per-pod
  grant, independent of org membership) is untouched.
- `visible_event_ids` gains a third source: events where the identity has
  an `OWNER`/`ORGANIZER` `OrganizationMember` row on that event's org —
  closing issue #72 item 2.
- Migration: synthesize `OrganizationMember` rows from every surviving
  `EventOrganizer` row before dropping the table, so pre-existing events
  (including those in Phase 11's placeholder "Unassigned" org) don't lose
  their organizers.
- `EventOrganizer` model, table, and dual-write removed entirely.
- `GET /organizations/{id}/members` and
  `DELETE /organizations/{id}/members/{member_id}` (issue #72 item 1) —
  mirrors `pod_roles.py`'s `list_pod_roles`/`revoke_pod_role`.

**Out of scope (explicitly deferred):**
- Issue #72 item 3 (`NewEvent.tsx` test-harness workaround) — frontend
  test hygiene, unrelated to this phase's backend cutover.
- Issue #72 item 4 (`nginx.conf` SPA-collision guard for a future
  `/organizations/*` client route) — tracked for Phase 13, no route
  exists yet to collide.
- Any capability differentiation for `SCOREKEEPER`/`JUDGE` org roles
  (unchanged from Phase 11 — reserved for a future phase).
- Any org-management UI (Phase 13, FR33).
- No frontend changes at all — confirmed zero `EventOrganizer`/organizer
  references anywhere in `frontend/src`; the auth cutover is invisible to
  the UI.

## 2. Data model

No new tables. `Organization`/`OrganizationMember` (Phase 11) are the
sole grant mechanism for organizer-level access going forward.
`EventOrganizer` (`backend/app/models/rbac.py`) is deleted along with its
`event_organizers` table. `PodRole`/`PodRoleName` (same file) are
unchanged.

## 3. Authorization logic (`backend/app/auth/dependencies.py`)

```python
def event_organizer_exists(db: Session, identity: Identity, event_id: uuid.UUID) -> bool:
    event = db.get(Event, event_id)
    if event is None:
        return False
    role = org_member_role(db, identity, event.organization_id)
    return role in (OrgRoleName.OWNER, OrgRoleName.ORGANIZER)
```

`require_event_organizer`, `require_pod_organizer`, `pod_access_allowed`,
`pod_staff_allowed`, `require_pod_access` keep their existing signatures
and call sites — only `event_organizer_exists`'s body changes, so every
downstream function that composes it inherits the new behavior for free.

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
    pod_ids = {...}  # unchanged
    pod_event_ids = {...}  # unchanged
    return org_event_ids | pod_event_ids
```

(`EventOrganizer`-sourced ids removed since the table is gone; the org-role
join replaces it and additionally covers every org member with
`OWNER`/`ORGANIZER`, not just the event's original creator.)

## 4. Routers

- `events.py` `create_event`: remove the `EventOrganizer(...)` dual-write.
  Access for the creator is already covered — they must be `OWNER`/
  `ORGANIZER` on `organization_id` to pass the existing
  `org_member_role` check, and that membership is now the sole source of
  truth.
- `events.py` `delete_event`: remove the
  `db.query(EventOrganizer).filter_by(event_id=event_id).delete()` line
  (nothing left to clean up).
- `pods.py`, `entries.py`, `rounds.py`, `pod_roles.py`, `matches.py`: no
  changes — they call the unchanged function names.
- `organizations.py`: add
  ```
  GET /organizations/{id}/members
    Auth: get_current_identity; caller must have an OrganizationMember
    row on {id} (any role), else 403. 404 if org doesn't exist.
    Returns list[OrganizationMemberRead].

  DELETE /organizations/{id}/members/{member_id}
    Auth: require_org_owner (existing dependency).
    404 if the member row doesn't exist or isn't on {id}.
    Deletes the row. 204.
  ```

## 5. Migration (0012)

One Alembic migration, runs before the code deploying the new
authorization logic:

```python
def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO organization_members
            (id, organization_id, player_uuid, source_system, role, created_at)
        SELECT gen_random_uuid(), e.organization_id, eo.player_uuid, eo.source_system,
               'organizer', now()
        FROM event_organizers eo
        JOIN events e ON e.id = eo.event_id
        ON CONFLICT ON CONSTRAINT uq_org_member_identity DO NOTHING
    """))
    op.drop_table("event_organizers")

def downgrade() -> None:
    # Recreates event_organizers empty, mirroring 0006's original definition
    # exactly (columns, FK, unique constraint, both indexes). Synthesized
    # OrganizationMember rows are NOT reverse-migrated out — downgrade is a
    # schema-only revert, not a data revert.
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

This covers pre-existing events (including those backfilled into Phase
11's placeholder "Unassigned" org) — every surviving `EventOrganizer` row
becomes an equivalent `OrganizationMember` row before the table is
dropped, so no event silently loses its organizer.

## 6. Issue #72 disposition

- **Item 1 (revocation)**: in scope, §4.
- **Item 2 (OWNER visibility gap)**: in scope, §3 (`visible_event_ids`).
- **Item 3 (`NewEvent.tsx` test workaround)**: out of scope, unrelated
  frontend test-hygiene nit — left on issue #72 for whenever that file is
  next touched.
- **Item 4 (`nginx.conf` SPA-collision guard)**: out of scope, tracked for
  Phase 13 when a `/organizations/*` client route actually exists.

## 7. Testing

- **Migration**: real-Postgres testcontainer test (mirrors 0011's
  pattern) — seed an `EventOrganizer` row pre-migration, run migration
  0012, assert an equivalent `OrganizationMember` row exists and
  `event_organizers` is gone. Also seed a case where the identity is
  already an `OrganizationMember` on that org (conflict path) and assert
  no duplicate/error.
- **Integration**: org OWNER can GET/PATCH/DELETE an event, and
  create pods/entries/rounds under it, that a different org ORGANIZER
  member created (closes issue #72 item 2) — and the symmetric case
  (ORGANIZER operating on an OWNER-created event). `GET/DELETE
  /organizations/{id}/members`: OWNER can list and revoke; non-owner
  member gets 403 on DELETE; 404 for unknown org id or member id not
  belonging to that org; revoked member loses event/pod access on the
  next call.
- **Regression**: existing suite must pass with `EventOrganizer`
  references removed. Most existing tests create org+event with the same
  identity (already `OWNER`, so unaffected by the cutover) — only
  `test_auth_dependencies.py`, `test_rbac_models.py`, and
  `test_events_api.py` construct `EventOrganizer` rows directly and need
  rework onto `OrganizationMember` fixtures. Final grep for
  `EventOrganizer`/`event_organizer` across `backend/` must return
  nothing outside migration 0012's historical SQL/downgrade.

## 8. Open questions

None outstanding — all sections reviewed and approved with the owner
during brainstorming (2026-08-13).
