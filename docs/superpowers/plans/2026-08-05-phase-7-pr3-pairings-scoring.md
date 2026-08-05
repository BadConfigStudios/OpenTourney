# Phase 7 PR3 — Pairings/Seating + BO1 Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `/pods/:podId/pairings` screen — current-round pairings with seating, round-history selector, inline BO1 result entry gated by persona, "Generate Next Round" — closing FR20/FR21.

**Architecture:** Small backend addition (a `method` field on `Match`, defaulting `"manual_entry"`) plus a frontend-only screen built on the existing React Query + `apiRequest`/`jsonInit` + `msw` patterns from PR2 (`EventDetail.tsx`, `EntryRoster.tsx`). One `useQuery` fetches all rounds (no per-round endpoint exists), one fetches entries for name lookup; local component state tracks which round is selected.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend), React + TypeScript + `@tanstack/react-query` + `react-router` + `msw`/Vitest/Testing Library (frontend). No new dependencies.

## Global Constraints

- TDD throughout (RED → GREEN, test written and confirmed failing before implementation) — spec's NFR1.
- UI gates the result-entry controls and "Generate Next Round" by `currentPersona.role` only (`organizer`/`scorekeeper`/`player`) — no per-pod fine-grained self-check exists on the backend for a Scorekeeper persona (`GET /pods/{id}/roles` is Organizer-only). The backend's `pod_staff_allowed`/`require_pod_organizer` checks remain the real enforcement.
- `method` is fixed to the literal `"manual_entry"` for now — no dual-submission/dispute-reconciliation model in this PR (tracked as issue #40).
- Follow existing patterns exactly: `apiRequest`/`jsonInit` (`frontend/src/api/request.ts`) for all new API functions; `msw` network-layer mocking (`frontend/src/test/server.ts`) for component tests, including stateful handlers wherever a mutation must be reflected in a subsequent GET (see `EntryRoster.test.tsx` for the pattern); `ErrorBanner` for all error display; alembic migration numbering `NNNN_description.py` continuing from `0008`.
- Backend integration tests duplicate the `_create_pod`/`_auth_headers`/`_add_entry` helpers locally per file (existing convention — no shared helper module) rather than introducing one.
- Stage files by name in commits, never `git add -A`/`.`. Conventional Commits format + `Co-Authored-By: Claude <noreply@anthropic.com>`.

---

### Task 1: Backend — `method` field on `Match`

**Files:**
- Create: `backend/alembic/versions/0009_add_match_method.py`
- Modify: `backend/app/models/match.py`
- Modify: `backend/app/schemas/match.py`
- Modify: `backend/app/routers/matches.py`
- Modify: `backend/tests/integration/test_matches_api.py`
- Modify: `backend/tests/integration/test_round_match_models.py`

**Interfaces:**
- Produces: `Match.method: str` (default `"manual_entry"`); `MatchRead.method: str`; `MatchResultUpdate.method: Literal["manual_entry"] = "manual_entry"`. Later tasks (frontend `api/matches.ts`) send `method: "manual_entry"` explicitly in every POST body and expect it back in the response.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/integration/test_round_match_models.py`, add after `test_match_defaults_to_unreported`:

```python
def test_match_defaults_method_to_manual_entry(db_session):
    pod, entry1, entry2 = _make_pod_with_two_entries(db_session)
    round_ = Round(pod_id=pod.id, number=1)
    db_session.add(round_)
    db_session.flush()

    match = Match(round_id=round_.id, entry1_id=entry1.id, entry2_id=entry2.id)
    db_session.add(match)
    db_session.commit()

    assert match.method == "manual_entry"
```

In `backend/tests/integration/test_matches_api.py`, modify `test_organizer_reports_match_result` to add a `method` assertion, and add a new test for an explicit `method` in the request body:

```python
def test_organizer_reports_match_result(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    _, match_id = _pod_with_one_match(api_client, token)

    response = api_client.post(
        f"/matches/{match_id}/result", json={"result": "entry1_win"}, headers=_auth_headers(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "entry1_win"
    assert body["reported_by"] == body["witnessed_by"]
    assert body["reported_by"] is not None
    assert body["method"] == "manual_entry"


def test_reporting_result_accepts_explicit_manual_entry_method(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    _, match_id = _pod_with_one_match(api_client, token)

    response = api_client.post(
        f"/matches/{match_id}/result",
        json={"result": "entry1_win", "method": "manual_entry"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["method"] == "manual_entry"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/integration/test_round_match_models.py::test_match_defaults_method_to_manual_entry tests/integration/test_matches_api.py::test_organizer_reports_match_result tests/integration/test_matches_api.py::test_reporting_result_accepts_explicit_manual_entry_method -v`

Expected: FAIL — `AttributeError: 'Match' object has no attribute 'method'` (model test) and `KeyError: 'method'` (API tests, since the response body has no such key yet).

- [ ] **Step 3: Write the migration**

Create `backend/alembic/versions/0009_add_match_method.py`:

```python
"""add method to matches

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-05

"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("method", sa.String(), nullable=False, server_default="manual_entry"),
    )


def downgrade() -> None:
    op.drop_column("matches", "method")
```

- [ ] **Step 4: Update the model**

In `backend/app/models/match.py`, add the `method` column to the `Match` class, immediately after the `result` column definition (before `reported_by`):

```python
    method: Mapped[str] = mapped_column(String, nullable=False, default="manual_entry")
```

- [ ] **Step 5: Update the schemas**

In `backend/app/schemas/match.py`:

```python
class MatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    round_id: uuid.UUID
    entry1_id: uuid.UUID
    entry2_id: uuid.UUID | None
    result: MatchResult
    reported_by: str | None
    witnessed_by: str | None
    table_number: int | None
    method: str


class MatchResultUpdate(BaseModel):
    result: Literal[MatchResult.ENTRY1_WIN, MatchResult.ENTRY2_WIN, MatchResult.TIE]
    method: Literal["manual_entry"] = "manual_entry"
```

- [ ] **Step 6: Update the router to persist `method`**

In `backend/app/routers/matches.py`, in `report_match_result`, add one line after `match.result = payload.result`:

```python
    reporter = f"{identity.source_system}:{identity.player_uuid}"
    match.result = payload.result
    match.method = payload.method
    match.reported_by = reporter
    match.witnessed_by = reporter
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && pytest tests/integration/test_round_match_models.py tests/integration/test_matches_api.py -v`

Expected: PASS (all tests in both files, including the two pre-existing suites — confirms nothing else broke).

- [ ] **Step 8: Commit**

```bash
git add backend/alembic/versions/0009_add_match_method.py backend/app/models/match.py backend/app/schemas/match.py backend/app/routers/matches.py backend/tests/integration/test_matches_api.py backend/tests/integration/test_round_match_models.py
git commit -m "feat(backend): add method field to match result reporting"
```

---

### Task 2: Frontend — `api/matches.ts`

**Files:**
- Create: `frontend/src/api/matches.ts`
- Test: `frontend/src/api/matches.test.ts`

**Interfaces:**
- Consumes: `apiRequest<T>(apiFetch, path, init?)`, `jsonInit(method, body)`, `type ApiFetch` from `./request` (`frontend/src/api/request.ts:1,13,49`).
- Produces: `interface MatchRead { id, round_id, entry1_id, entry2_id: string | null, result: MatchResult, reported_by: string | null, witnessed_by: string | null, table_number: number | null, method: string }`; `type MatchResult = "unreported" | "entry1_win" | "entry2_win" | "tie"`; `function reportMatchResult(apiFetch, matchId: string, result: "entry1_win" | "entry2_win" | "tie"): Promise<MatchRead>`. Task 3 (`api/rounds.ts`) imports `MatchRead`; Tasks 4-6 (`Pairings.tsx`) import `MatchRead` and `reportMatchResult`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/matches.test.ts`:

```typescript
import { describe, expect, it, vi } from "vitest";
import { reportMatchResult } from "./matches";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

describe("matches api", () => {
  it("reportMatchResult POSTs the result with a fixed manual_entry method", async () => {
    const apiFetch = fetchReturning({ id: "m1" });

    await reportMatchResult(apiFetch, "m1", "entry1_win");

    expect(apiFetch).toHaveBeenCalledWith("/matches/m1/result", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ result: "entry1_win", method: "manual_entry" }),
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/matches.test.ts`
Expected: FAIL — `Cannot find module './matches'`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/api/matches.ts`:

```typescript
import { apiRequest, jsonInit, type ApiFetch } from "./request";

export type MatchResult = "unreported" | "entry1_win" | "entry2_win" | "tie";

export interface MatchRead {
  id: string;
  round_id: string;
  entry1_id: string;
  entry2_id: string | null;
  result: MatchResult;
  reported_by: string | null;
  witnessed_by: string | null;
  table_number: number | null;
  method: string;
}

export function reportMatchResult(
  apiFetch: ApiFetch,
  matchId: string,
  result: "entry1_win" | "entry2_win" | "tie",
): Promise<MatchRead> {
  return apiRequest(
    apiFetch,
    `/matches/${matchId}/result`,
    jsonInit("POST", { result, method: "manual_entry" }),
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/api/matches.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/matches.ts frontend/src/api/matches.test.ts
git commit -m "feat(frontend): add matches API client for BO1 result reporting"
```

---

### Task 3: Frontend — `api/rounds.ts`

**Files:**
- Create: `frontend/src/api/rounds.ts`
- Test: `frontend/src/api/rounds.test.ts`

**Interfaces:**
- Consumes: `apiRequest`, `type ApiFetch` from `./request`; `type MatchRead` from `./matches` (Task 2).
- Produces: `interface RoundRead { id: string; pod_id: string; number: number; matches: MatchRead[] }`; `function fetchRounds(apiFetch, podId: string): Promise<RoundRead[]>`; `function generateRound(apiFetch, podId: string): Promise<RoundRead>`. Tasks 4-6 (`Pairings.tsx`) import both functions and `RoundRead`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api/rounds.test.ts`:

```typescript
import { describe, expect, it, vi } from "vitest";
import { fetchRounds, generateRound } from "./rounds";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

describe("rounds api", () => {
  it("fetchRounds GETs /pods/:id/rounds", async () => {
    const apiFetch = fetchReturning([]);

    await fetchRounds(apiFetch, "pod-1");

    expect(apiFetch).toHaveBeenCalledWith("/pods/pod-1/rounds", undefined);
  });

  it("generateRound POSTs /pods/:id/rounds with no body", async () => {
    const apiFetch = fetchReturning({ id: "r1" }, 201);

    await generateRound(apiFetch, "pod-1");

    expect(apiFetch).toHaveBeenCalledWith("/pods/pod-1/rounds", { method: "POST" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/rounds.test.ts`
Expected: FAIL — `Cannot find module './rounds'`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/api/rounds.ts`:

```typescript
import { apiRequest, type ApiFetch } from "./request";
import type { MatchRead } from "./matches";

export interface RoundRead {
  id: string;
  pod_id: string;
  number: number;
  matches: MatchRead[];
}

export function fetchRounds(apiFetch: ApiFetch, podId: string): Promise<RoundRead[]> {
  return apiRequest(apiFetch, `/pods/${podId}/rounds`);
}

export function generateRound(apiFetch: ApiFetch, podId: string): Promise<RoundRead> {
  return apiRequest(apiFetch, `/pods/${podId}/rounds`, { method: "POST" });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/api/rounds.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/rounds.ts frontend/src/api/rounds.test.ts
git commit -m "feat(frontend): add rounds API client"
```

---

### Task 4: Frontend — Pairings screen: round fetch, entry names, bye rows, round-history selector

**Files:**
- Create: `frontend/src/routes/Pairings.tsx`
- Modify: `frontend/src/routes/router.tsx`
- Test: `frontend/src/routes/Pairings.test.tsx`

**Interfaces:**
- Consumes: `fetchRounds`, `type RoundRead` (Task 3); `listEntries`, `type EntryRead` from `../api/entries` (existing, `frontend/src/api/entries.ts:3,13`); `useAuth` from `../auth/AuthContext` (existing, exposes `{ apiFetch, currentPersona, setPersona }`); `ErrorBanner` from `../components/ErrorBanner` (existing).
- Produces: `export function Pairings()` — rendered at route `pods/:podId/pairings`. Tasks 5-6 add to this same component/file (result-entry buttons, Generate Next Round).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/routes/Pairings.test.tsx`:

```tsx
import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { Pairings } from "./Pairings";

const ENTRIES = [
  {
    id: "e1",
    pod_id: "pod-1",
    player_uuid: "u1",
    source_system: "opentourney-ui",
    metadata: { display_name: "Ash" },
  },
  {
    id: "e2",
    pod_id: "pod-1",
    player_uuid: "u2",
    source_system: "opentourney-ui",
    metadata: { display_name: "Misty" },
  },
];

const ROUND_1 = {
  id: "r1",
  pod_id: "pod-1",
  number: 1,
  matches: [
    {
      id: "m1",
      round_id: "r1",
      entry1_id: "e1",
      entry2_id: "e2",
      result: "entry1_win",
      reported_by: "opentourney-ui:organizer-uuid",
      witnessed_by: "opentourney-ui:organizer-uuid",
      table_number: 1,
      method: "manual_entry",
    },
  ],
};

export const ROUND_2 = {
  id: "r2",
  pod_id: "pod-1",
  number: 2,
  matches: [
    {
      id: "m2",
      round_id: "r2",
      entry1_id: "e1",
      entry2_id: null,
      result: "unreported",
      reported_by: null,
      witnessed_by: null,
      table_number: null,
      method: "manual_entry",
    },
  ],
};

function renderPairings(personaLabel?: string) {
  renderWithProviders(<Pairings />, {
    path: "/pods/pod-1/pairings",
    routePath: "/pods/:podId/pairings",
    personaLabel,
  });
}

describe("Pairings", () => {
  it("shows the latest round's pairings by default, with entry names and table numbers", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_1, ROUND_2])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderPairings();

    expect(await screen.findByText(/Ash — \(bye\)/)).toBeInTheDocument();
  });

  it("shows a past round's matches, read-only, when selected from round history", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_1, ROUND_2])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderPairings();
    await screen.findByText(/Ash — \(bye\)/);

    fireEvent.click(screen.getByRole("button", { name: "Round 1" }));

    expect(await screen.findByText(/Table 1: Ash vs Misty/)).toBeInTheDocument();
  });

  it("shows a message when no rounds have been generated yet", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderPairings();

    expect(await screen.findByText("No rounds generated yet.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/routes/Pairings.test.tsx`
Expected: FAIL — `Cannot find module './Pairings'`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/routes/Pairings.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import { listEntries, type EntryRead } from "../api/entries";
import { fetchRounds } from "../api/rounds";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

function displayNameFor(entries: EntryRead[] | undefined, entryId: string): string {
  const entry = entries?.find((candidate) => candidate.id === entryId);
  return entry?.metadata.display_name ?? entryId;
}

export function Pairings() {
  const { podId } = useParams<{ podId: string }>();
  if (!podId) throw new Error("Pairings rendered without a podId route param");

  const { apiFetch } = useAuth();

  const roundsQuery = useQuery({
    queryKey: ["rounds", podId],
    queryFn: () => fetchRounds(apiFetch, podId),
  });
  const entriesQuery = useQuery({
    queryKey: ["entries", podId],
    queryFn: () => listEntries(apiFetch, podId),
  });

  const rounds = roundsQuery.data ?? [];
  const latestRound = rounds[rounds.length - 1];

  const [selectedRoundNumber, setSelectedRoundNumber] = useState<number | null>(null);
  const effectiveRoundNumber = selectedRoundNumber ?? latestRound?.number ?? null;
  const selectedRound = rounds.find((round) => round.number === effectiveRoundNumber);

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">Pairings</h2>
      <ErrorBanner error={roundsQuery.error ?? entriesQuery.error} />

      {rounds.length === 0 && !roundsQuery.isLoading && <p>No rounds generated yet.</p>}

      {rounds.length > 0 && (
        <div className="mb-4 flex gap-2">
          {rounds.map((round) => (
            <button
              key={round.number}
              onClick={() => setSelectedRoundNumber(round.number)}
              className="rounded border border-gray-300 px-2 py-1 text-sm"
            >
              Round {round.number}
            </button>
          ))}
        </div>
      )}

      {selectedRound && (
        <ul className="divide-y divide-gray-200">
          {selectedRound.matches.map((match) => (
            <li key={match.id} className="py-2">
              {match.entry2_id === null ? (
                <span>{displayNameFor(entriesQuery.data, match.entry1_id)} — (bye)</span>
              ) : (
                <span>
                  Table {match.table_number}: {displayNameFor(entriesQuery.data, match.entry1_id)} vs{" "}
                  {displayNameFor(entriesQuery.data, match.entry2_id)}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

In `frontend/src/routes/router.tsx`, replace the placeholder pairings route:

```tsx
import { createBrowserRouter } from "react-router";
import { EventDetail } from "./EventDetail";
import { EventList } from "./EventList";
import { Layout } from "./Layout";
import { NewEvent } from "./NewEvent";
import { Pairings } from "./Pairings";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <EventList /> },
      { path: "events/new", element: <NewEvent /> },
      { path: "events/:eventId", element: <EventDetail /> },
      { path: "pods/:podId/pairings", element: <Pairings /> },
      { path: "pods/:podId/report", element: <div>Report</div> },
    ],
  },
]);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/routes/Pairings.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/Pairings.tsx frontend/src/routes/Pairings.test.tsx frontend/src/routes/router.tsx
git commit -m "feat(frontend): add Pairings screen with round history and bye handling"
```

---

### Task 5: Frontend — Pairings screen: inline BO1 result entry, persona-gated

**Files:**
- Modify: `frontend/src/routes/Pairings.tsx`
- Modify: `frontend/src/routes/Pairings.test.tsx`

**Interfaces:**
- Consumes: `reportMatchResult` from `../api/matches` (Task 2); `useMutation`, `useQueryClient` from `@tanstack/react-query`; `currentPersona.role` from `useAuth()` (existing, `PersonaRole = "organizer" | "scorekeeper" | "player"`).
- Produces: no new exports — result-entry UI added to the existing `Pairings` component from Task 4.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/routes/Pairings.test.tsx` (new top-level fixture plus new `it` blocks inside the existing `describe("Pairings", ...)`):

```tsx
const ROUND_3_UNREPORTED = {
  id: "r3",
  pod_id: "pod-1",
  number: 3,
  matches: [
    {
      id: "m3",
      round_id: "r3",
      entry1_id: "e1",
      entry2_id: "e2",
      result: "unreported",
      reported_by: null,
      witnessed_by: null,
      table_number: 1,
      method: "manual_entry",
    },
  ],
};
```

```tsx
it("lets the Organizer report a result via inline buttons", async () => {
  let matches = [{ ...ROUND_3_UNREPORTED.matches[0] }];
  server.use(
    http.get("/pods/pod-1/rounds", () => HttpResponse.json([{ ...ROUND_3_UNREPORTED, matches }])),
    http.get("/entries", () => HttpResponse.json(ENTRIES)),
    http.post("/matches/m3/result", async ({ request }) => {
      const body = (await request.json()) as { result: string };
      matches = [{ ...matches[0], result: body.result }];
      return HttpResponse.json(matches[0]);
    }),
  );

  renderPairings();
  fireEvent.click(await screen.findByRole("button", { name: "Ash wins" }));

  expect(await screen.findByText(/entry1_win/)).toBeInTheDocument();
});

it("shows result buttons for the Scorekeeper persona too", async () => {
  server.use(
    http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_3_UNREPORTED])),
    http.get("/entries", () => HttpResponse.json(ENTRIES)),
  );

  renderPairings("Scorekeeper");

  expect(await screen.findByRole("button", { name: "Ash wins" })).toBeInTheDocument();
});

it("hides result buttons for the Player persona", async () => {
  server.use(
    http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_3_UNREPORTED])),
    http.get("/entries", () => HttpResponse.json(ENTRIES)),
  );

  renderPairings("Player");

  await screen.findByText(/Table 1: Ash vs Misty/);
  expect(screen.queryByRole("button", { name: "Ash wins" })).not.toBeInTheDocument();
});

it("shows an already-reported match's result as text instead of buttons", async () => {
  server.use(
    http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_1])),
    http.get("/entries", () => HttpResponse.json(ENTRIES)),
  );

  renderPairings();

  expect(await screen.findByText(/entry1_win/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Ash wins" })).not.toBeInTheDocument();
});

it("hides result buttons on a past round even for the Organizer", async () => {
  const pastUnreported = { ...ROUND_3_UNREPORTED, number: 1 };
  server.use(
    http.get("/pods/pod-1/rounds", () => HttpResponse.json([pastUnreported, ROUND_2])),
    http.get("/entries", () => HttpResponse.json(ENTRIES)),
  );

  renderPairings();
  await screen.findByText(/Ash — \(bye\)/);

  fireEvent.click(screen.getByRole("button", { name: "Round 1" }));

  await screen.findByText(/Table 1: Ash vs Misty/);
  expect(screen.queryByRole("button", { name: "Ash wins" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/routes/Pairings.test.tsx`
Expected: FAIL — the 5 new tests fail (`Ash wins` button not found / result text not found); the 3 Task-4 tests still pass.

- [ ] **Step 3: Write the implementation**

In `frontend/src/routes/Pairings.tsx`, update imports and add the mutation + button rendering:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import { listEntries, type EntryRead } from "../api/entries";
import { reportMatchResult } from "../api/matches";
import { fetchRounds } from "../api/rounds";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";
```

Inside `Pairings()`, after the `entriesQuery` declaration:

```tsx
  const { currentPersona } = useAuth();
  const queryClient = useQueryClient();
  const canReport = currentPersona.role === "organizer" || currentPersona.role === "scorekeeper";

  const reportMutation = useMutation({
    mutationFn: (args: { matchId: string; result: "entry1_win" | "entry2_win" | "tie" }) =>
      reportMatchResult(apiFetch, args.matchId, args.result),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rounds", podId] }),
  });
```

(Note: `useAuth()` is already called once for `apiFetch` — extend that existing destructure to `const { apiFetch, currentPersona } = useAuth();` rather than calling `useAuth()` twice.)

Update the `ErrorBanner` line:

```tsx
      <ErrorBanner error={roundsQuery.error ?? entriesQuery.error ?? reportMutation.error} />
```

Add `isLatestRound` next to `selectedRound`:

```tsx
  const isLatestRound = effectiveRoundNumber !== null && effectiveRoundNumber === latestRound?.number;
```

Replace the non-bye match rendering branch:

```tsx
              {match.entry2_id === null ? (
                <span>{displayNameFor(entriesQuery.data, match.entry1_id)} — (bye)</span>
              ) : match.result !== "unreported" ? (
                <span>
                  Table {match.table_number}: {displayNameFor(entriesQuery.data, match.entry1_id)} vs{" "}
                  {displayNameFor(entriesQuery.data, match.entry2_id)} — {match.result}
                </span>
              ) : (
                <span>
                  Table {match.table_number}: {displayNameFor(entriesQuery.data, match.entry1_id)} vs{" "}
                  {displayNameFor(entriesQuery.data, match.entry2_id)}
                  {canReport && isLatestRound && (
                    <span className="ml-2 inline-flex gap-2">
                      <button
                        onClick={() => reportMutation.mutate({ matchId: match.id, result: "entry1_win" })}
                      >
                        {displayNameFor(entriesQuery.data, match.entry1_id)} wins
                      </button>
                      <button onClick={() => reportMutation.mutate({ matchId: match.id, result: "tie" })}>
                        Tie
                      </button>
                      <button
                        onClick={() => reportMutation.mutate({ matchId: match.id, result: "entry2_win" })}
                      >
                        {displayNameFor(entriesQuery.data, match.entry2_id)} wins
                      </button>
                    </span>
                  )}
                </span>
              )}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/routes/Pairings.test.tsx`
Expected: PASS (all 8 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/Pairings.tsx frontend/src/routes/Pairings.test.tsx
git commit -m "feat(frontend): add inline BO1 result entry to Pairings, gated by persona"
```

---

### Task 6: Frontend — Pairings screen: Generate Next Round

**Files:**
- Modify: `frontend/src/routes/Pairings.tsx`
- Modify: `frontend/src/routes/Pairings.test.tsx`

**Interfaces:**
- Consumes: `generateRound` from `../api/rounds` (Task 3).
- Produces: no new exports.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/routes/Pairings.test.tsx`:

```tsx
it("lets the Organizer generate the next round and auto-selects it", async () => {
  let rounds = [ROUND_1];
  server.use(
    http.get("/pods/pod-1/rounds", () => HttpResponse.json(rounds)),
    http.get("/entries", () => HttpResponse.json(ENTRIES)),
    http.post("/pods/pod-1/rounds", () => {
      rounds = [...rounds, ROUND_2];
      return HttpResponse.json(ROUND_2, { status: 201 });
    }),
  );

  renderPairings();
  await screen.findByText(/Table 1: Ash vs Misty/);

  fireEvent.click(screen.getByRole("button", { name: "Generate Next Round" }));

  expect(await screen.findByText(/Ash — \(bye\)/)).toBeInTheDocument();
});

it("disables Generate Next Round while the latest round has an unreported match", async () => {
  server.use(
    http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_3_UNREPORTED])),
    http.get("/entries", () => HttpResponse.json(ENTRIES)),
  );

  renderPairings();

  expect(await screen.findByRole("button", { name: "Generate Next Round" })).toBeDisabled();
});

it("hides Generate Next Round for non-Organizer personas", async () => {
  server.use(
    http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_1])),
    http.get("/entries", () => HttpResponse.json(ENTRIES)),
  );

  renderPairings("Scorekeeper");

  await screen.findByText(/Table 1: Ash vs Misty/);
  expect(screen.queryByRole("button", { name: "Generate Next Round" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/routes/Pairings.test.tsx`
Expected: FAIL — the 3 new tests fail (`Generate Next Round` button not found); the earlier 8 tests still pass.

- [ ] **Step 3: Write the implementation**

In `frontend/src/routes/Pairings.tsx`, update the import from `../api/rounds`:

```tsx
import { fetchRounds, generateRound } from "../api/rounds";
```

After the `reportMutation` declaration, add:

```tsx
  const isOrganizer = currentPersona.role === "organizer";
  const latestRoundHasUnreportedMatch =
    latestRound?.matches.some((match) => match.entry2_id !== null && match.result === "unreported") ?? false;

  const generateMutation = useMutation({
    mutationFn: () => generateRound(apiFetch, podId),
    onSuccess: (newRound) => {
      queryClient.invalidateQueries({ queryKey: ["rounds", podId] });
      setSelectedRoundNumber(newRound.number);
    },
  });
```

Update the `ErrorBanner` line:

```tsx
      <ErrorBanner
        error={roundsQuery.error ?? entriesQuery.error ?? reportMutation.error ?? generateMutation.error}
      />
```

Add the button, right after the `ErrorBanner` line:

```tsx
      {isOrganizer && (
        <button
          onClick={() => generateMutation.mutate()}
          disabled={rounds.length > 0 && latestRoundHasUnreportedMatch}
          title={
            latestRoundHasUnreportedMatch
              ? "All matches in the current round must be reported first"
              : undefined
          }
          className="mb-4 rounded bg-blue-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          Generate Next Round
        </button>
      )}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/routes/Pairings.test.tsx`
Expected: PASS (all 11 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/Pairings.tsx frontend/src/routes/Pairings.test.tsx
git commit -m "feat(frontend): add Generate Next Round action to Pairings"
```

---

### Task 7: Frontend — link into Pairings from EventDetail

**Files:**
- Modify: `frontend/src/routes/EventDetail.tsx`
- Modify: `frontend/src/routes/EventDetail.test.tsx`

**Interfaces:**
- Consumes: `Link` from `react-router` (already a project dependency, used via `RouterProvider`/`createBrowserRouter` elsewhere).
- Produces: no new exports — a link added to the existing `EventDetail` component.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/routes/EventDetail.test.tsx`, inside the existing `describe("EventDetail", ...)`:

```tsx
  it("links to the pairings screen once a pod exists", async () => {
    server.use(
      http.get("/events/event-1", () => HttpResponse.json(EVENT)),
      http.get("/pods", () => HttpResponse.json([POD])),
      http.get("/entries", () => HttpResponse.json([])),
    );

    renderDetail();

    expect(await screen.findByRole("link", { name: "View Pairings" })).toHaveAttribute(
      "href",
      "/pods/pod-1/pairings",
    );
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/routes/EventDetail.test.tsx`
Expected: FAIL — no element with role `link` and name `View Pairings`.

- [ ] **Step 3: Write the implementation**

In `frontend/src/routes/EventDetail.tsx`, add the `Link` import:

```tsx
import { Link, useParams } from "react-router";
```

Replace the final render block:

```tsx
      {pod && (
        <>
          <p className="mb-4">
            <Link to={`/pods/${pod.id}/pairings`} className="text-blue-600 underline">
              View Pairings
            </Link>
          </p>
          <EntryRoster podId={pod.id} />
        </>
      )}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/routes/EventDetail.test.tsx`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/EventDetail.tsx frontend/src/routes/EventDetail.test.tsx
git commit -m "feat(frontend): link from EventDetail to the Pairings screen"
```

---

### Task 8: Backend — integration test mirroring the Pairings screen's full flow

**Files:**
- Create: `backend/tests/integration/test_pairings_flow_api.py`

**Interfaces:**
- Consumes: `api_client`, `make_token` fixtures (`backend/tests/integration/conftest.py:68,86`) — same pattern as `test_setup_flow_api.py` and `test_matches_api.py`.
- Produces: nothing consumed by later tasks — this is the final task.

- [ ] **Step 1: Write the test**

Create `backend/tests/integration/test_pairings_flow_api.py`:

```python
import uuid


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_pod(api_client, token) -> str:
    event_id = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    ).json()["id"]
    return api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    ).json()["id"]


def _add_entry(api_client, token, pod_id) -> str:
    return api_client.post(
        "/entries",
        json={
            "pod_id": pod_id,
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "metadata": {},
        },
        headers=_auth_headers(token),
    ).json()["id"]


def test_pairings_screen_flow_generate_report_generate_next_round(api_client, make_token):
    """Mirrors the Phase 7 PR3 Pairings screen's sequence of API calls:
    generate round one, report both matches, generate round two, and
    confirm round history accumulates with the reported results intact.
    """
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    for _ in range(4):
        _add_entry(api_client, token, pod_id)

    round1 = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    assert round1["number"] == 1
    assert len(round1["matches"]) == 2

    for match in round1["matches"]:
        response = api_client.post(
            f"/matches/{match['id']}/result",
            json={"result": "entry1_win", "method": "manual_entry"},
            headers=_auth_headers(token),
        )
        assert response.status_code == 200
        assert response.json()["method"] == "manual_entry"

    round2 = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    assert round2["number"] == 2

    rounds = api_client.get(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    assert [r["number"] for r in rounds] == [1, 2]
    assert all(m["result"] == "entry1_win" for m in rounds[0]["matches"])
    assert all(m["result"] == "unreported" for m in rounds[1]["matches"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/integration/test_pairings_flow_api.py -v`
Expected: FAIL initially only if run before Task 1 lands (missing `method` in response causes the `assert response.json()["method"] == "manual_entry"` line to raise `KeyError`). If run after Task 1, skip straight to Step 3 — there is no new production code this task adds, so this test should already pass. Run it anyway to confirm the full flow works end-to-end.

- [ ] **Step 3: Run test to verify it passes**

Run: `cd backend && pytest tests/integration/test_pairings_flow_api.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_pairings_flow_api.py
git commit -m "test(backend): add integration test for the pairings screen's full round flow"
```

---

## After all tasks

Run the full test suites once more before opening a PR:

```bash
cd backend && pytest -v
cd frontend && npx vitest run
```

Per the mandatory manual verification gate (not a subagent task): bring the app up against staging, walk through Organizer generates round → reports result → generates next round; Scorekeeper reports a result; Player sees pairings read-only with no controls — before merging.
