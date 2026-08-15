# Phase 13 — Organization Management UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a real UI (plus the two supporting backend endpoints) to view an organization's member roster, add/remove members, change member roles, and rename the organization — closing out the Organization/RBAC sub-project (FR33, issue #70).

**Architecture:** Two new FastAPI endpoints (`GET /organizations/{id}`, `PATCH /organizations/{id}`, `PATCH /organizations/{id}/members/{member_id}`) reusing the existing `require_org_owner`/`org_member_role` auth dependencies and the lockout-guard pattern already proven in `revoke_organization_member`. Two new React routes (`Organizations.tsx` list/redirect, `OrganizationDetail.tsx` roster + owner controls) wired into the existing router/nav, following the fetch/mutate/`ErrorBanner` pattern already used by `EventDetail.tsx` and `NewEvent.tsx`. One nginx location-block edit to extend the SPA-collision guard to `/organizations/*`.

**Tech Stack:** Python/FastAPI/SQLAlchemy/Pydantic (backend), React/TypeScript/@tanstack/react-query/react-router/MSW+Vitest (frontend), Alembic not needed (no schema change).

## Global Constraints

- Owner-only actions (`PATCH /organizations/{id}`, `PATCH .../members/{id}`, add/remove member) all gate through `require_org_owner`, exactly as the existing add/revoke endpoints do — no new auth dependency.
- Role-demotion-to-non-OWNER must reuse the exact `with_for_update()` lockout guard from `revoke_organization_member` (`backend/app/routers/organizations.py:126-141`) — same 409 detail string `"cannot revoke the organization's only owner"`.
- No player-search/directory endpoint exists anywhere in the codebase (identities come from JWT claims) — add-member UI stays raw UUID + source_system text entry, matching `NewEvent.tsx`'s org-creation form conventions.
- Frontend gating for the "Organizations" nav link and owner-only controls uses `currentPersona.role === "organizer"` / `viewer_role === "owner"` string checks — same pattern as `NewEvent.tsx:56` and `EventDetail.tsx:15`.
- All new frontend API calls go through the existing `apiRequest`/`jsonInit` helpers in `frontend/src/api/request.ts` — no new fetch wrapper.
- Out of scope: `NewEvent.tsx` changes, any player-directory/search endpoint, any change to `visible_event_ids`/RBAC resolution (done in Phase 12).

---

### Task 1: Backend — `GET /organizations/{id}` (org detail with viewer_role)

**Files:**
- Modify: `backend/app/schemas/organization.py`
- Modify: `backend/app/routers/organizations.py`
- Test: `backend/tests/integration/test_organizations_api.py`

**Interfaces:**
- Consumes: `org_member_role(db, identity, organization_id)` from `app/auth/dependencies.py` (existing, returns `OrgRoleName | None`).
- Produces: `OrganizationDetailRead` schema (`id: uuid.UUID`, `name: str`, `viewer_role: OrgRoleName`) for Task 3's frontend `getOrganization` client and Task 5's `OrganizationDetail.tsx` to consume.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/integration/test_organizations_api.py`:

```python
def test_get_organization_returns_name_and_viewer_role(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)

    response = api_client.get(f"/organizations/{org_id}", headers=_auth_headers(owner_token))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == org_id
    assert body["name"] == "Dragon's Den"
    assert body["viewer_role"] == "owner"


def test_get_organization_reflects_non_owner_viewer_role(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    staff_uuid = str(uuid.uuid4())
    api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "scorekeeper"},
        headers=_auth_headers(owner_token),
    )
    staff_token = make_token(
        player_uuid=uuid.UUID(staff_uuid), source_system="club-checkin", roles=["organizer"]
    )

    response = api_client.get(f"/organizations/{org_id}", headers=_auth_headers(staff_token))

    assert response.status_code == 200
    assert response.json()["viewer_role"] == "scorekeeper"


def test_get_organization_404s_for_unknown_org(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.get(f"/organizations/{uuid.uuid4()}", headers=_auth_headers(token))

    assert response.status_code == 404


def test_get_organization_403s_for_non_member(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.get(f"/organizations/{org_id}", headers=_auth_headers(stranger_token))

    assert response.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/integration/test_organizations_api.py -k get_organization -v`
Expected: FAIL — `404 Not Found` for all four (route doesn't exist yet), not the expected status codes.

- [ ] **Step 3: Add `OrganizationDetailRead` schema**

In `backend/app/schemas/organization.py`, after `OrganizationRead`:

```python
class OrganizationDetailRead(OrganizationRead):
    viewer_role: OrgRoleName
```

- [ ] **Step 4: Add the route**

In `backend/app/routers/organizations.py`, add `OrganizationDetailRead` to the `from app.schemas.organization import (...)` block, then add this route (placed after `list_organizations`, before `add_organization_member`):

```python
@router.get("/{organization_id}", response_model=OrganizationDetailRead)
def get_organization(
    organization_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> dict:
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="organization not found")
    role = org_member_role(db, identity, organization_id)
    if role is None:
        raise HTTPException(status_code=403, detail="not a member of this organization")
    return {"id": org.id, "name": org.name, "viewer_role": role}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/integration/test_organizations_api.py -k get_organization -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Run the full organizations test file to check for regressions**

Run: `cd backend && python -m pytest tests/integration/test_organizations_api.py -v`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/organization.py backend/app/routers/organizations.py backend/tests/integration/test_organizations_api.py
git commit -m "feat(backend): add GET /organizations/{id} with viewer_role"
```

---

### Task 2: Backend — `PATCH /organizations/{id}` (rename) and `PATCH /organizations/{id}/members/{member_id}` (role change)

**Files:**
- Modify: `backend/app/schemas/organization.py`
- Modify: `backend/app/routers/organizations.py`
- Test: `backend/tests/integration/test_organizations_api.py`

**Interfaces:**
- Consumes: `require_org_owner` dependency (existing); the lockout-guard pattern from `revoke_organization_member` (`backend/app/routers/organizations.py:126-141`, this task copies its `with_for_update()` query and 409 detail string).
- Produces: `OrganizationRead` (rename response) and `OrganizationMemberRead` (role-change response) — both already exist and are consumed by Task 3's `updateOrganization`/`updateOrganizationMember` clients.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/integration/test_organizations_api.py`:

```python
def test_owner_renames_organization(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)

    response = api_client.patch(
        f"/organizations/{org_id}", json={"name": "New Name"}, headers=_auth_headers(owner_token)
    )

    assert response.status_code == 200
    assert response.json()["name"] == "New Name"
    get_response = api_client.get(f"/organizations/{org_id}", headers=_auth_headers(owner_token))
    assert get_response.json()["name"] == "New Name"


def test_non_owner_cannot_rename_organization(api_client, make_token):
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

    response = api_client.patch(
        f"/organizations/{org_id}", json={"name": "New Name"}, headers=_auth_headers(staff_token)
    )

    assert response.status_code == 403


def test_rename_404s_for_unknown_org(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.patch(
        f"/organizations/{uuid.uuid4()}", json={"name": "New Name"}, headers=_auth_headers(token)
    )

    assert response.status_code == 404


def test_owner_changes_member_role(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    staff_uuid = str(uuid.uuid4())
    add_response = api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "scorekeeper"},
        headers=_auth_headers(owner_token),
    )
    member_id = add_response.json()["id"]

    response = api_client.patch(
        f"/organizations/{org_id}/members/{member_id}",
        json={"role": "organizer"},
        headers=_auth_headers(owner_token),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "organizer"


def test_non_owner_cannot_change_member_role(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    staff_uuid = str(uuid.uuid4())
    add_response = api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "scorekeeper"},
        headers=_auth_headers(owner_token),
    )
    member_id = add_response.json()["id"]
    staff_token = make_token(
        player_uuid=uuid.UUID(staff_uuid), source_system="club-checkin", roles=["organizer"]
    )

    response = api_client.patch(
        f"/organizations/{org_id}/members/{member_id}",
        json={"role": "organizer"},
        headers=_auth_headers(staff_token),
    )

    assert response.status_code == 403


def test_role_change_404s_for_member_not_belonging_to_org(api_client, make_token):
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

    response = api_client.patch(
        f"/organizations/{org_id}/members/{member_id}",
        json={"role": "scorekeeper"},
        headers=_auth_headers(owner_token),
    )

    assert response.status_code == 404


def test_demoting_the_only_owner_returns_409(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    members_response = api_client.get(
        f"/organizations/{org_id}/members", headers=_auth_headers(owner_token)
    )
    owner_member_id = members_response.json()[0]["id"]

    response = api_client.patch(
        f"/organizations/{org_id}/members/{owner_member_id}",
        json={"role": "organizer"},
        headers=_auth_headers(owner_token),
    )

    assert response.status_code == 409
    get_response = api_client.get(f"/organizations/{org_id}/members", headers=_auth_headers(owner_token))
    assert get_response.json()[0]["role"] == "owner"


def test_demoting_one_of_multiple_owners_succeeds(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    members_response = api_client.get(
        f"/organizations/{org_id}/members", headers=_auth_headers(owner_token)
    )
    first_owner_member_id = members_response.json()[0]["id"]
    second_owner_uuid = str(uuid.uuid4())
    api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": second_owner_uuid, "source_system": "club-checkin", "role": "owner"},
        headers=_auth_headers(owner_token),
    )

    response = api_client.patch(
        f"/organizations/{org_id}/members/{first_owner_member_id}",
        json={"role": "scorekeeper"},
        headers=_auth_headers(owner_token),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "scorekeeper"


def test_changing_role_to_same_owner_role_does_not_trigger_lockout_guard(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    members_response = api_client.get(
        f"/organizations/{org_id}/members", headers=_auth_headers(owner_token)
    )
    owner_member_id = members_response.json()[0]["id"]

    response = api_client.patch(
        f"/organizations/{org_id}/members/{owner_member_id}",
        json={"role": "owner"},
        headers=_auth_headers(owner_token),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "owner"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/integration/test_organizations_api.py -k "rename or role or demoting or changing_role" -v`
Expected: FAIL — 404/405 for all (routes don't exist yet).

- [ ] **Step 3: Add `OrganizationUpdate` and `OrganizationMemberUpdate` schemas**

In `backend/app/schemas/organization.py`, after `OrganizationCreate`:

```python
class OrganizationUpdate(BaseModel):
    name: str
```

After `OrganizationMemberCreate`:

```python
class OrganizationMemberUpdate(BaseModel):
    role: OrgRoleName
```

- [ ] **Step 4: Add the two routes**

In `backend/app/routers/organizations.py`, update the schema import to include `OrganizationMemberUpdate` and `OrganizationUpdate`, then add these routes (rename after `get_organization`; role-change after `add_organization_member`, before `list_organization_members`):

```python
@router.patch("/{organization_id}", response_model=OrganizationRead)
def update_organization(
    organization_id: uuid.UUID,
    payload: OrganizationUpdate,
    identity: Identity = Depends(require_org_owner),
    db: Session = Depends(get_db_session),
) -> Organization:
    org = db.get(Organization, organization_id)
    org.name = payload.name
    db.commit()
    db.refresh(org)
    return org
```

```python
@router.patch("/{organization_id}/members/{member_id}", response_model=OrganizationMemberRead)
def update_organization_member(
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: OrganizationMemberUpdate,
    identity: Identity = Depends(require_org_owner),
    db: Session = Depends(get_db_session),
) -> OrganizationMember:
    member = db.get(OrganizationMember, member_id)
    if member is None or member.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="organization member not found")
    if member.role == OrgRoleName.OWNER and payload.role != OrgRoleName.OWNER:
        # Same with_for_update() lockout guard as revoke_organization_member
        # (backend/app/routers/organizations.py) — a demotion away from OWNER
        # is equivalent to a revocation for lockout purposes.
        owner_rows = (
            db.query(OrganizationMember)
            .filter_by(organization_id=organization_id, role=OrgRoleName.OWNER)
            .with_for_update()
            .all()
        )
        if len(owner_rows) <= 1:
            raise HTTPException(
                status_code=409, detail="cannot revoke the organization's only owner"
            )
    member.role = payload.role
    db.commit()
    db.refresh(member)
    return member
```

`require_org_owner` already 404s for an unknown `organization_id` before either handler body runs, covering the rename-404 test.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/integration/test_organizations_api.py -k "rename or role or demoting or changing_role" -v`
Expected: PASS (9 passed)

- [ ] **Step 6: Run the full backend test suite to check for regressions**

Run: `cd backend && python -m pytest -v`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/organization.py backend/app/routers/organizations.py backend/tests/integration/test_organizations_api.py
git commit -m "feat(backend): add org rename and member role-change endpoints"
```

---

### Task 3: Frontend API client — organizations.ts additions

**Files:**
- Modify: `frontend/src/api/organizations.ts`
- Test: `frontend/src/api/organizations.test.ts`

**Interfaces:**
- Consumes: `apiRequest`, `jsonInit`, `ApiFetch` from `./request` (existing).
- Produces: `OrganizationDetailRead` (`id`, `name`, `viewer_role`), `OrganizationMemberRead` (`id`, `organization_id`, `player_uuid`, `source_system`, `role`) types, and functions `getOrganization`, `updateOrganization`, `listOrganizationMembers`, `addOrganizationMember`, `updateOrganizationMember`, `removeOrganizationMember` — all consumed by Task 5 (`Organizations.tsx`, `OrganizationDetail.tsx`).

- [ ] **Step 1: Write the failing tests**

`frontend/src/api/organizations.test.ts` currently reads:

```typescript
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

Update the import line to add the six new functions, and append these `it`s inside the existing `describe("organizations api", ...)` block (reusing the file's own `fetchReturning` helper — do not introduce a different mocking style):

```typescript
import {
  addOrganizationMember,
  createOrganization,
  getOrganization,
  listOrganizations,
  listOrganizationMembers,
  removeOrganizationMember,
  updateOrganization,
  updateOrganizationMember,
} from "./organizations";
```

```typescript
  it("getOrganization GETs /organizations/:id", async () => {
    const apiFetch = fetchReturning({ id: "org-1", name: "Dragon's Den", viewer_role: "owner" });

    const org = await getOrganization(apiFetch, "org-1");

    expect(org).toEqual({ id: "org-1", name: "Dragon's Den", viewer_role: "owner" });
    expect(apiFetch).toHaveBeenCalledWith("/organizations/org-1", undefined);
  });

  it("updateOrganization PATCHes the new name", async () => {
    const apiFetch = fetchReturning({ id: "org-1", name: "New Name" });

    await updateOrganization(apiFetch, "org-1", "New Name");

    expect(apiFetch).toHaveBeenCalledWith("/organizations/org-1", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "New Name" }),
    });
  });

  it("listOrganizationMembers GETs /organizations/:id/members", async () => {
    const members = [
      { id: "m1", organization_id: "org-1", player_uuid: "p1", source_system: "club-checkin", role: "owner" },
    ];
    const apiFetch = fetchReturning(members);

    const result = await listOrganizationMembers(apiFetch, "org-1");

    expect(result).toEqual(members);
    expect(apiFetch).toHaveBeenCalledWith("/organizations/org-1/members", undefined);
  });

  it("addOrganizationMember POSTs the new member", async () => {
    const member = { id: "m2", organization_id: "org-1", player_uuid: "p2", source_system: "club-checkin", role: "scorekeeper" };
    const apiFetch = fetchReturning(member, 201);

    await addOrganizationMember(apiFetch, "org-1", "p2", "club-checkin", "scorekeeper");

    expect(apiFetch).toHaveBeenCalledWith("/organizations/org-1/members", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_uuid: "p2", source_system: "club-checkin", role: "scorekeeper" }),
    });
  });

  it("updateOrganizationMember PATCHes the member's role", async () => {
    const member = { id: "m2", organization_id: "org-1", player_uuid: "p2", source_system: "club-checkin", role: "organizer" };
    const apiFetch = fetchReturning(member);

    await updateOrganizationMember(apiFetch, "org-1", "m2", "organizer");

    expect(apiFetch).toHaveBeenCalledWith("/organizations/org-1/members/m2", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: "organizer" }),
    });
  });

  it("removeOrganizationMember DELETEs the member", async () => {
    const apiFetch = fetchReturning(undefined, 204);

    await removeOrganizationMember(apiFetch, "org-1", "m2");

    expect(apiFetch).toHaveBeenCalledWith("/organizations/org-1/members/m2", { method: "DELETE" });
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/api/organizations.test.ts`
Expected: FAIL — the new functions don't exist yet (TypeScript/import errors).

- [ ] **Step 3: Implement the client functions**

Replace the full contents of `frontend/src/api/organizations.ts`:

```typescript
import { apiRequest, jsonInit, type ApiFetch } from "./request";

export interface OrganizationRead {
  id: string;
  name: string;
}

export type OrgRoleName = "owner" | "organizer" | "scorekeeper" | "judge";

export interface OrganizationDetailRead extends OrganizationRead {
  viewer_role: OrgRoleName;
}

export interface OrganizationMemberRead {
  id: string;
  organization_id: string;
  player_uuid: string;
  source_system: string;
  role: OrgRoleName;
}

export function listOrganizations(apiFetch: ApiFetch): Promise<OrganizationRead[]> {
  return apiRequest(apiFetch, "/organizations");
}

export function createOrganization(apiFetch: ApiFetch, name: string): Promise<OrganizationRead> {
  return apiRequest(apiFetch, "/organizations", jsonInit("POST", { name }));
}

export function getOrganization(apiFetch: ApiFetch, organizationId: string): Promise<OrganizationDetailRead> {
  return apiRequest(apiFetch, `/organizations/${organizationId}`);
}

export function updateOrganization(
  apiFetch: ApiFetch,
  organizationId: string,
  name: string,
): Promise<OrganizationRead> {
  return apiRequest(apiFetch, `/organizations/${organizationId}`, jsonInit("PATCH", { name }));
}

export function listOrganizationMembers(
  apiFetch: ApiFetch,
  organizationId: string,
): Promise<OrganizationMemberRead[]> {
  return apiRequest(apiFetch, `/organizations/${organizationId}/members`);
}

export function addOrganizationMember(
  apiFetch: ApiFetch,
  organizationId: string,
  playerUuid: string,
  sourceSystem: string,
  role: OrgRoleName,
): Promise<OrganizationMemberRead> {
  return apiRequest(
    apiFetch,
    `/organizations/${organizationId}/members`,
    jsonInit("POST", { player_uuid: playerUuid, source_system: sourceSystem, role }),
  );
}

export function updateOrganizationMember(
  apiFetch: ApiFetch,
  organizationId: string,
  memberId: string,
  role: OrgRoleName,
): Promise<OrganizationMemberRead> {
  return apiRequest(
    apiFetch,
    `/organizations/${organizationId}/members/${memberId}`,
    jsonInit("PATCH", { role }),
  );
}

export function removeOrganizationMember(
  apiFetch: ApiFetch,
  organizationId: string,
  memberId: string,
): Promise<void> {
  return apiRequest(apiFetch, `/organizations/${organizationId}/members/${memberId}`, { method: "DELETE" });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/api/organizations.test.ts`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/organizations.ts frontend/src/api/organizations.test.ts
git commit -m "feat(frontend): add organization detail/rename/member-management API client"
```

---

### Task 4: Frontend — `Organizations.tsx` (list/redirect route)

**Files:**
- Create: `frontend/src/routes/Organizations.tsx`
- Test: `frontend/src/routes/Organizations.test.tsx`
- Modify: `frontend/src/routes/router.tsx`

**Interfaces:**
- Consumes: `listOrganizations` from `../api/organizations` (existing), `useAuth` from `../auth/AuthContext` (existing, gives `apiFetch`), `ErrorBanner` from `../components/ErrorBanner` (existing).
- Produces: `Organizations` component, mounted at route path `/organizations` in `router.tsx`, consumed by Task 6's nav link.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/routes/Organizations.test.tsx`:

```typescript
import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { Organizations } from "./Organizations";

describe("Organizations", () => {
  beforeEach(() => localStorage.clear());

  it("redirects straight to the detail page when the caller belongs to exactly one organization", async () => {
    server.use(
      http.get("/organizations", () => HttpResponse.json([{ id: "org-1", name: "Dragon's Den" }])),
    );

    renderWithProviders(<Organizations />, { path: "/organizations" });

    expect(await screen.findByTestId("navigated-to")).toHaveTextContent("/organizations/org-1");
  });

  it("lists all organizations as links when the caller belongs to more than one", async () => {
    server.use(
      http.get("/organizations", () =>
        HttpResponse.json([
          { id: "org-1", name: "Dragon's Den" },
          { id: "org-2", name: "Second Store" },
        ]),
      ),
    );

    renderWithProviders(<Organizations />, { path: "/organizations" });

    expect(await screen.findByRole("link", { name: "Dragon's Den" })).toHaveAttribute(
      "href",
      "/organizations/org-1",
    );
    expect(screen.getByRole("link", { name: "Second Store" })).toHaveAttribute(
      "href",
      "/organizations/org-2",
    );
  });

  it("shows an empty state when the caller belongs to no organizations", async () => {
    server.use(http.get("/organizations", () => HttpResponse.json([])));

    renderWithProviders(<Organizations />, { path: "/organizations" });

    expect(await screen.findByText("You don't belong to any organizations yet.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/routes/Organizations.test.tsx`
Expected: FAIL — `Cannot find module './Organizations'`.

- [ ] **Step 3: Implement `Organizations.tsx`**

```typescript
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate } from "react-router";
import { listOrganizations } from "../api/organizations";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

export function Organizations() {
  const { apiFetch } = useAuth();
  const organizationsQuery = useQuery({
    queryKey: ["organizations"],
    queryFn: () => listOrganizations(apiFetch),
  });

  const organizations = organizationsQuery.data ?? [];

  if (organizationsQuery.isSuccess && organizations.length === 1) {
    return <Navigate to={`/organizations/${organizations[0].id}`} replace />;
  }

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">Organizations</h2>
      <ErrorBanner error={organizationsQuery.error} />

      {organizationsQuery.isSuccess && organizations.length === 0 && (
        <p className="text-sm text-gray-600">You don't belong to any organizations yet.</p>
      )}

      {organizations.length > 1 && (
        <ul>
          {organizations.map((org) => (
            <li key={org.id} className="mb-1">
              <Link to={`/organizations/${org.id}`} className="text-blue-600 underline">
                {org.name}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Wire the route**

In `frontend/src/routes/router.tsx`, add the import `import { Organizations } from "./Organizations";` and a new child route `{ path: "organizations", element: <Organizations /> },` (placed after the `index: true` route, before `events/new`).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/routes/Organizations.test.tsx`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/Organizations.tsx frontend/src/routes/Organizations.test.tsx frontend/src/routes/router.tsx
git commit -m "feat(frontend): add Organizations list/redirect route"
```

---

### Task 5: Frontend — `OrganizationDetail.tsx` (roster + owner controls)

**Files:**
- Create: `frontend/src/routes/OrganizationDetail.tsx`
- Test: `frontend/src/routes/OrganizationDetail.test.tsx`
- Modify: `frontend/src/routes/router.tsx`

**Interfaces:**
- Consumes: `getOrganization`, `updateOrganization`, `listOrganizationMembers`, `addOrganizationMember`, `updateOrganizationMember`, `removeOrganizationMember`, `OrgRoleName` from `../api/organizations` (Task 3); `useAuth`, `ErrorBanner` (existing).
- Produces: `OrganizationDetail` component mounted at `/organizations/:id` in `router.tsx`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/routes/OrganizationDetail.test.tsx`:

```typescript
import { fireEvent, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { OrganizationDetail } from "./OrganizationDetail";

const OWNER_ORG = { id: "org-1", name: "Dragon's Den", viewer_role: "owner" };
const ORGANIZER_ORG = { id: "org-1", name: "Dragon's Den", viewer_role: "organizer" };
const MEMBERS = [
  { id: "m1", organization_id: "org-1", player_uuid: "p1", source_system: "club-checkin", role: "owner" },
  { id: "m2", organization_id: "org-1", player_uuid: "p2", source_system: "club-checkin", role: "scorekeeper" },
];

function renderDetail() {
  renderWithProviders(<OrganizationDetail />, {
    path: "/organizations/org-1",
    routePath: "/organizations/:organizationId",
  });
}

describe("OrganizationDetail", () => {
  beforeEach(() => localStorage.clear());

  it("shows the roster with identity and role for any member", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(ORGANIZER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
    );

    renderDetail();

    await screen.findByText("Dragon's Den");
    expect(screen.getByText("p1")).toBeInTheDocument();
    expect(screen.getByText("p2")).toBeInTheDocument();
  });

  it("hides owner-only controls for a non-owner member", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(ORGANIZER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
    );

    renderDetail();

    await screen.findByText("Dragon's Den");
    expect(screen.queryByLabelText("Organization name")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("New member player UUID")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
  });

  it("shows rename, add-member, per-row role select, and remove for an owner", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(OWNER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
    );

    renderDetail();

    await screen.findByText("Dragon's Den");
    expect(screen.getByLabelText("Organization name")).toBeInTheDocument();
    expect(screen.getByLabelText("New member player UUID")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(2);
  });

  it("renames the organization", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(OWNER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
      http.patch("/organizations/org-1", async ({ request }) => {
        const body = (await request.json()) as { name: string };
        return HttpResponse.json({ id: "org-1", name: body.name });
      }),
    );

    renderDetail();

    await screen.findByText("Dragon's Den");
    fireEvent.change(screen.getByLabelText("Organization name"), { target: { value: "New Name" } });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));

    expect(await screen.findByText("New Name")).toBeInTheDocument();
  });

  it("adds a new member", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(OWNER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
      http.post("/organizations/org-1/members", async ({ request }) => {
        const body = (await request.json()) as { player_uuid: string; source_system: string; role: string };
        return HttpResponse.json(
          { id: "m3", organization_id: "org-1", player_uuid: body.player_uuid, source_system: body.source_system, role: body.role },
          { status: 201 },
        );
      }),
    );

    renderDetail();

    await screen.findByText("Dragon's Den");
    fireEvent.change(screen.getByLabelText("New member player UUID"), { target: { value: "p3" } });
    fireEvent.change(screen.getByLabelText("New member source system"), { target: { value: "club-checkin" } });
    fireEvent.change(screen.getByLabelText("New member role"), { target: { value: "judge" } });
    fireEvent.click(screen.getByRole("button", { name: "Add member" }));

    expect(await screen.findByText("p3")).toBeInTheDocument();
  });

  it("changes a member's role", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(OWNER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
      http.patch("/organizations/org-1/members/m2", async ({ request }) => {
        const body = (await request.json()) as { role: string };
        return HttpResponse.json({ id: "m2", organization_id: "org-1", player_uuid: "p2", source_system: "club-checkin", role: body.role });
      }),
    );

    renderDetail();

    await screen.findByText("Dragon's Den");
    const row = screen.getByText("p2").closest("tr");
    if (!row) throw new Error("expected a table row for p2");
    fireEvent.change(within(row).getByRole("combobox"), { target: { value: "organizer" } });

    expect(await within(row).findByText("organizer")).toBeInTheDocument();
  });

  it("removes a member", async () => {
    let members = MEMBERS;
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(OWNER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(members)),
      http.delete("/organizations/org-1/members/m2", () => {
        members = members.filter((member) => member.id !== "m2");
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderDetail();

    await screen.findByText("p2");
    const row = screen.getByText("p2").closest("tr");
    if (!row) throw new Error("expected a table row for p2");
    fireEvent.click(within(row).getByRole("button", { name: "Remove" }));

    await screen.findByText("Dragon's Den");
    expect(screen.queryByText("p2")).not.toBeInTheDocument();
  });

  it("surfaces the lockout-guard 409 inline", async () => {
    server.use(
      http.get("/organizations/org-1", () => HttpResponse.json(OWNER_ORG)),
      http.get("/organizations/org-1/members", () => HttpResponse.json(MEMBERS)),
      http.delete("/organizations/org-1/members/m1", () =>
        HttpResponse.json({ detail: "cannot revoke the organization's only owner" }, { status: 409 }),
      ),
    );

    renderDetail();

    await screen.findByText("p1");
    const row = screen.getByText("p1").closest("tr");
    if (!row) throw new Error("expected a table row for p1");
    fireEvent.click(within(row).getByRole("button", { name: "Remove" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("cannot revoke the organization's only owner");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/routes/OrganizationDetail.test.tsx`
Expected: FAIL — `Cannot find module './OrganizationDetail'`.

- [ ] **Step 3: Implement `OrganizationDetail.tsx`**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import {
  addOrganizationMember,
  getOrganization,
  listOrganizationMembers,
  removeOrganizationMember,
  updateOrganization,
  updateOrganizationMember,
  type OrgRoleName,
} from "../api/organizations";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

const ROLE_OPTIONS: OrgRoleName[] = ["owner", "organizer", "scorekeeper", "judge"];

export function OrganizationDetail() {
  const { organizationId } = useParams<{ organizationId: string }>();
  if (!organizationId) throw new Error("OrganizationDetail rendered without an organizationId route param");

  const { apiFetch } = useAuth();
  const queryClient = useQueryClient();
  const [nameDraft, setNameDraft] = useState("");
  const [newPlayerUuid, setNewPlayerUuid] = useState("");
  const [newSourceSystem, setNewSourceSystem] = useState("");
  const [newRole, setNewRole] = useState<OrgRoleName>("scorekeeper");

  const orgQuery = useQuery({
    queryKey: ["organizations", organizationId],
    queryFn: () => getOrganization(apiFetch, organizationId),
  });
  const membersQuery = useQuery({
    queryKey: ["organizations", organizationId, "members"],
    queryFn: () => listOrganizationMembers(apiFetch, organizationId),
    enabled: orgQuery.isSuccess,
  });

  const renameMutation = useMutation({
    mutationFn: () => updateOrganization(apiFetch, organizationId, nameDraft),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["organizations", organizationId] }),
  });

  const addMemberMutation = useMutation({
    mutationFn: () => addOrganizationMember(apiFetch, organizationId, newPlayerUuid, newSourceSystem, newRole),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizations", organizationId, "members"] });
      setNewPlayerUuid("");
      setNewSourceSystem("");
      setNewRole("scorekeeper");
    },
  });

  const updateRoleMutation = useMutation({
    mutationFn: ({ memberId, role }: { memberId: string; role: OrgRoleName }) =>
      updateOrganizationMember(apiFetch, organizationId, memberId, role),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["organizations", organizationId, "members"] }),
  });

  const removeMemberMutation = useMutation({
    mutationFn: (memberId: string) => removeOrganizationMember(apiFetch, organizationId, memberId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["organizations", organizationId, "members"] }),
  });

  const org = orgQuery.data;
  const members = membersQuery.data ?? [];
  const isOwner = org?.viewer_role === "owner";

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">{org ? org.name : "…"}</h2>
      <ErrorBanner
        error={
          orgQuery.error ??
          membersQuery.error ??
          renameMutation.error ??
          addMemberMutation.error ??
          updateRoleMutation.error ??
          removeMemberMutation.error
        }
      />

      {isOwner && (
        <div className="mb-6">
          <label className="block text-sm">
            Organization name
            <input
              type="text"
              value={nameDraft || org.name}
              onChange={(event) => setNameDraft(event.target.value)}
              className="mt-1 block rounded border border-gray-300 px-2 py-1"
            />
          </label>
          <button
            type="button"
            disabled={renameMutation.isPending}
            onClick={() => renameMutation.mutate()}
            className="mt-2 rounded border border-gray-300 px-3 py-1.5 text-sm"
          >
            Save name
          </button>
        </div>
      )}

      <table className="mb-6 w-full text-left text-sm">
        <thead>
          <tr>
            <th className="border-b border-gray-200 pb-1">Identity</th>
            <th className="border-b border-gray-200 pb-1">Role</th>
            {isOwner && <th className="border-b border-gray-200 pb-1" />}
          </tr>
        </thead>
        <tbody>
          {members.map((member) => (
            <tr key={member.id}>
              <td className="py-1">{member.player_uuid}</td>
              <td className="py-1">
                {isOwner ? (
                  <select
                    value={member.role}
                    onChange={(event) =>
                      updateRoleMutation.mutate({ memberId: member.id, role: event.target.value as OrgRoleName })
                    }
                    className="rounded border border-gray-300 px-2 py-1"
                  >
                    {ROLE_OPTIONS.map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </select>
                ) : (
                  member.role
                )}
              </td>
              {isOwner && (
                <td className="py-1">
                  <button
                    type="button"
                    onClick={() => removeMemberMutation.mutate(member.id)}
                    disabled={removeMemberMutation.isPending}
                    className="rounded border border-gray-300 px-2 py-1 text-xs"
                  >
                    Remove
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      {isOwner && (
        <div>
          <h3 className="mb-2 text-sm font-semibold">Add member</h3>
          <label className="block text-sm">
            New member player UUID
            <input
              type="text"
              value={newPlayerUuid}
              onChange={(event) => setNewPlayerUuid(event.target.value)}
              className="mt-1 block rounded border border-gray-300 px-2 py-1"
            />
          </label>
          <label className="mt-2 block text-sm">
            New member source system
            <input
              type="text"
              value={newSourceSystem}
              onChange={(event) => setNewSourceSystem(event.target.value)}
              className="mt-1 block rounded border border-gray-300 px-2 py-1"
            />
          </label>
          <label className="mt-2 block text-sm">
            New member role
            <select
              value={newRole}
              onChange={(event) => setNewRole(event.target.value as OrgRoleName)}
              className="mt-1 block rounded border border-gray-300 px-2 py-1"
            >
              {ROLE_OPTIONS.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={addMemberMutation.isPending || newPlayerUuid.trim() === "" || newSourceSystem.trim() === ""}
            onClick={() => addMemberMutation.mutate()}
            className="mt-2 rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
          >
            Add member
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Wire the route**

In `frontend/src/routes/router.tsx`, add the import `import { OrganizationDetail } from "./OrganizationDetail";` and a new child route `{ path: "organizations/:organizationId", element: <OrganizationDetail /> },` (placed right after the `organizations` route added in Task 4).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/routes/OrganizationDetail.test.tsx`
Expected: PASS (8 passed)

- [ ] **Step 6: Run the full frontend test suite to check for regressions**

Run: `cd frontend && npx vitest run`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add frontend/src/routes/OrganizationDetail.tsx frontend/src/routes/OrganizationDetail.test.tsx frontend/src/routes/router.tsx
git commit -m "feat(frontend): add OrganizationDetail roster and owner controls"
```

---

### Task 6: Frontend nav link + nginx SPA-collision guard

**Files:**
- Modify: `frontend/src/routes/Layout.tsx`
- Test: `frontend/src/routes/Layout.test.tsx` (create if it doesn't exist — check first)
- Modify: `frontend/nginx.conf`

**Interfaces:**
- Consumes: `useAuth` (existing, gives `currentPersona`), `Link` from `react-router`.
- Produces: nothing consumed by later tasks — this is the last task.

- [ ] **Step 1: Check for an existing Layout test file**

Run: `ls frontend/src/routes/Layout.test.tsx 2>/dev/null || echo "none"`

If it exists, read it first and match its conventions for the new test below. If not, create it fresh as in Step 2.

- [ ] **Step 2: Write the failing test**

Create (or add to) `frontend/src/routes/Layout.test.tsx`:

```typescript
import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { renderWithProviders } from "../test/renderWithProviders";
import { Layout } from "./Layout";

describe("Layout", () => {
  beforeEach(() => localStorage.clear());

  it("shows an Organizations nav link for an Organizer persona", async () => {
    renderWithProviders(<Layout />, { path: "/" });

    expect(await screen.findByRole("link", { name: "Organizations" })).toHaveAttribute(
      "href",
      "/organizations",
    );
  });

  it("hides the Organizations nav link for a non-Organizer persona", async () => {
    renderWithProviders(<Layout />, { path: "/", personaLabel: "Player" });

    await screen.findByText("OpenTourney");
    expect(screen.queryByRole("link", { name: "Organizations" })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/routes/Layout.test.tsx`
Expected: FAIL — no "Organizations" link found.

- [ ] **Step 4: Add the nav link**

Replace `frontend/src/routes/Layout.tsx`:

```typescript
import { Link, Outlet } from "react-router";
import { PersonaSwitcher } from "../auth/PersonaSwitcher";
import { useAuth } from "../auth/AuthContext";

export function Layout() {
  const { currentPersona } = useAuth();

  return (
    <div className="min-h-screen">
      <header className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
        <div className="flex items-center gap-4">
          <h1 className="font-semibold">OpenTourney</h1>
          {currentPersona.role === "organizer" && (
            <Link to="/organizations" className="text-sm text-blue-600 underline">
              Organizations
            </Link>
          )}
        </div>
        <PersonaSwitcher />
      </header>
      <main className="p-4">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/routes/Layout.test.tsx`
Expected: PASS (2 passed)

- [ ] **Step 6: Apply the nginx SPA-collision guard**

In `frontend/nginx.conf`, replace the `/organizations` location block (and its now-stale comment) with the same `$accepts_html` pattern used by `/events`, `/pods`, `/entries`, `/matches`:

```nginx
    location /organizations {
        if ($accepts_html) {
            return 418;
        }
        proxy_pass http://backend:8000;
    }
```

- [ ] **Step 7: Run the full frontend test suite to check for regressions**

Run: `cd frontend && npx vitest run`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add frontend/src/routes/Layout.tsx frontend/src/routes/Layout.test.tsx frontend/nginx.conf
git commit -m "feat(frontend): add Organizations nav link and nginx SPA-collision guard"
```

---

### Task 7: Final verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && python -m pytest -v`
Expected: all pass

- [ ] **Step 2: Run backend lint**

Run: `cd backend && ruff check .`
Expected: clean

- [ ] **Step 3: Run the full frontend suite**

Run: `cd frontend && npx vitest run`
Expected: all pass

- [ ] **Step 4: Run frontend typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean

- [ ] **Step 5: Run frontend lint (if configured)**

Run: `cd frontend && npx eslint . 2>&1 | tail -30` (check `package.json` scripts first for the project's actual lint command if this differs)
Expected: clean
