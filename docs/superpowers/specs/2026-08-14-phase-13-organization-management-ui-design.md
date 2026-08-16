# Phase 13 — Organization Management UI (FR33, issue #70)

## Context

Third phase of the Organization/RBAC sub-project:
- Phase 11 (PR #71): `Organization`/`OrganizationMember` data model, org-scoped event creation.
- Phase 12 (PR #73): RBAC cutover — `visible_event_ids` and event-organizer checks resolve via `OrganizationMember`; `GET`/`DELETE /organizations/{id}/members` shipped with an owner-lockout guard.

This phase closes the loop: a real UI to view an org's roster, add/remove members, change roles, and rename the org. Today the only org-related UI is `NewEvent.tsx`'s inline "create an org" stopgap.

Carried over from issue #72 (Phase 11 review follow-ups):
- Item 3 (`NewEvent.tsx`'s test-harness confirmation workaround) — **out of scope**. This phase does not touch `NewEvent.tsx`; item 3 stays deferred.
- Item 4 (`nginx.conf`'s `/organizations` proxy rule needs SPA-collision guard) — **in scope**, since this phase adds the first client-side route under `/organizations/*`.

## Backend

All new endpoints in `backend/app/routers/organizations.py`, reusing existing `require_org_owner` / `org_member_role` dependencies from `app/auth/dependencies.py`.

### `GET /organizations/{id}`
New. Returns the org's name plus the caller's own role in that org (`viewer_role`), so the frontend doesn't need to decode identity claims client-side to gate owner-only controls. 404 if the org doesn't exist; 403 if the caller has no `OrganizationMember` row for it (not just "role is None" — matches `list_organization_members`'s existing 403 pattern for non-owner/organizer, but here any non-member is rejected since even read access implies membership).

Response schema (`OrganizationDetailRead`, new in `schemas/organization.py`):
```python
class OrganizationDetailRead(OrganizationRead):
    viewer_role: OrgRoleName
```

### `PATCH /organizations/{id}`
New. Body `{name: str}`. Owner-only (`require_org_owner`). Renames the org, returns `OrganizationRead`.

### `PATCH /organizations/{id}/members/{member_id}`
New. Body `{role: OrgRoleName}`. Owner-only (`require_org_owner`). Updates an existing member's role in place.

When the update demotes a member away from `OWNER` to a non-`OWNER` role, reuse the exact lockout guard from `revoke_organization_member`: lock all `OWNER` rows for the org with `with_for_update()`, and reject with 409 (`"cannot revoke the organization's only owner"`) if the member being demoted is the sole owner. No guard needed when the new role is unchanged or when the member being updated isn't currently an `OWNER`.

Returns `OrganizationMemberRead`. 404 if `member_id` doesn't belong to `organization_id` (matches `revoke_organization_member`'s check).

### Unchanged
`POST /organizations/{id}/members` (add, 409 on duplicate identity), `GET /organizations/{id}/members` (list, owner/organizer only), `DELETE /organizations/{id}/members/{member_id}` (revoke, owner-only, existing lockout guard).

## Frontend

### API client (`frontend/src/api/organizations.ts`)
Add: `getOrganization`, `updateOrganization`, `listOrganizationMembers`, `addOrganizationMember`, `updateOrganizationMember`, `removeOrganizationMember`. Follow the existing `apiRequest`/`jsonInit` pattern already used by `listOrganizations`/`createOrganization`.

### Routes (`frontend/src/routes/router.tsx`)
- `/organizations` → `Organizations.tsx` (new). Fetches the caller's org list (existing `listOrganizations`). Exactly one org: redirect straight to `/organizations/:id`. More than one: render a simple list of links (name → `/organizations/:id`), no separate detail scaffolding needed for the list itself.
- `/organizations/:id` → `OrganizationDetail.tsx` (new). Fetches org detail (`getOrganization`, gives name + `viewer_role`) and member list (`listOrganizationMembers`, gated to owner/organizer by the backend already).

`OrganizationDetail.tsx` behavior:
- Always (any member): roster table — identity (`player_uuid` / `source_system`) + role per row.
- Only when `viewer_role === "owner"`:
  - Rename form (text input + save, calls `updateOrganization`).
  - Add-member form: `player_uuid` (text), `source_system` (text), `role` (`<select>` of the four `OrgRoleName` values: owner/organizer/scorekeeper/judge). No player-search/lookup endpoint exists anywhere in this codebase (identities come from JWT claims, not a queryable directory) — raw UUID + source_system entry is the only option, matching the existing precedent in `pod_roles.py`'s grant flow (which likewise has no frontend consumer yet).
  - Per-row role `<select>` (calls `updateOrganizationMember` on change) + remove button (calls `removeOrganizationMember`), each showing the backend's error inline (e.g. the 409 lockout message) via the existing `ErrorBanner` component.

### Nav (`frontend/src/routes/Layout.tsx`)
Layout currently has no persistent nav (`EventList` is the index route; `NewEvent` is reached via a button on `EventList` itself). This phase adds the first nav link: "Organizations", visible only when `currentPersona.role === "organizer"` (same gate `NewEvent.tsx` uses), pointing to `/organizations`.

### `nginx.conf`
Apply the existing `$accepts_html` / `return 418` pattern (already used for `/events`, `/pods`, `/entries`, `/matches`) to the `/organizations` location block, per the comment already there anticipating this phase.

## Testing

- Backend: unit tests for `GET /organizations/{id}` (viewer_role correctness, 403 for non-members, 404), `PATCH /organizations/{id}` (owner-only, 403 for non-owner), `PATCH /organizations/{id}/members/{member_id}` (role change, lockout-guard reuse on last-owner demotion, 404 for mismatched member/org), alongside the existing `test_organizations.py` conventions.
- Frontend: component tests for `Organizations.tsx` (single-org redirect, multi-org list) and `OrganizationDetail.tsx` (owner view shows all controls, organizer view is read-only roster, add/remove/role-change/rename call the right endpoints and reflect responses, lockout-guard 409 surfaces via `ErrorBanner`), MSW-mocked per `NewEvent.test.tsx` conventions.

## Out of scope

- Issue #72 item 3 (`NewEvent.tsx` inline-org-creation test-harness workaround) — not touched this phase, stays deferred.
- Player/identity search or directory — no such endpoint exists anywhere in the codebase; out of scope to add one here.
- Any changes to `visible_event_ids` / RBAC resolution logic — that's done, shipped in Phase 12 (PR #73).
