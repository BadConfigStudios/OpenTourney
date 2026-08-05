# Phase 7 PR2 — Event/Pod/Entry Setup Screens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder route stubs from Phase 7 PR1 with real Event list/create, Pod create, and Entry roster CRUD screens (FR19), wired to the existing Phase 5c/6 backend endpoints.

**Architecture:** Thin per-resource API helper modules (`src/api/events.ts`, `pods.ts`, `entries.ts`) built on a shared `apiRequest` wrapper around `AuthContext`'s existing `apiFetch`. React Query hooks in each screen call these helpers directly. Screens compose under the existing `router.tsx`/`Layout.tsx` shell from PR1.

**Tech Stack:** React 18, TypeScript, React Router 7, TanStack Query 5, Tailwind 4, Vitest + Testing Library, msw 2 (new, this PR).

## Global Constraints

- `msw` devDependency (`^2.15.0`) is confirmed for owner sign-off 2026-08-04 — log in `DECISIONS.md` (Task 1).
- Entry creation always generates `player_uuid` client-side via `crypto.randomUUID()` and sets `source_system` to the fixed value `"opentourney-ui"` — no manual UUID entry in this PR.
- Pod creation always sends `format_slug: "swiss"`, `game_slug: "generic"` with no visible form fields — only one format/game module exists.
- RBAC gating in the UI hides (does not merely disable) Organizer-only controls for non-Organizer personas. The backend remains the actual enforcement point; UI gating is convenience only.
- New screens live under `frontend/src/routes/`, new API helpers under `frontend/src/api/`, shared components under `frontend/src/components/`. Test files sit next to the file they test (`Foo.tsx` / `Foo.test.tsx`), matching PR1's existing layout.
- `frontend/vite.config.ts` already sets `restoreMocks: true` and `unstubGlobal: true` — component tests use `msw` (`frontend/src/test/server.ts`) to mock the network layer, not manual `fetch` stubs (existing `App.test.tsx`/`ConfigProvider.test.tsx`/`AuthContext.test.tsx` stub `fetch` directly for config-loading concerns only; don't change those files).
- Pairings (`/pods/:podId/pairings`) and report (`/pods/:podId/report`) routes stay untouched placeholder stubs — out of scope (PR3/PR4).

---

### Task 1: msw test infrastructure

**Files:**
- Modify: `frontend/package.json` (add `msw` devDependency)
- Create: `frontend/src/test/server.ts`
- Modify: `frontend/src/test/setup.ts`
- Test: `frontend/src/test/server.test.ts`
- Modify: `DECISIONS.md` (repo root)

**Interfaces:**
- Produces: `server` (msw `SetupServerApi` instance, from `frontend/src/test/server.ts`) — imported by every later component test to call `server.use(...)` for per-test handlers. Default handler: `GET /config.json` returns a 3-persona config (`Organizer`/`Scorekeeper`/`Player`, labels matching `frontend/public/config.json`'s shape).

- [ ] **Step 1: Install msw**

```bash
cd frontend && npm install --save-dev msw@^2.15.0
```

- [ ] **Step 2: Write the msw server module**

Create `frontend/src/test/server.ts`:

```ts
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

const DEFAULT_CONFIG = {
  personas: [
    { label: "Organizer", role: "organizer", token: "org-token" },
    { label: "Scorekeeper", role: "scorekeeper", token: "sk-token" },
    { label: "Player", role: "player", token: "player-token" },
  ],
};

export const server = setupServer(http.get("/config.json", () => HttpResponse.json(DEFAULT_CONFIG)));
```

- [ ] **Step 3: Wire server lifecycle into the test setup file**

Modify `frontend/src/test/setup.ts` to:

```ts
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

afterEach(() => {
  server.resetHandlers();
  cleanup();
});

afterAll(() => server.close());
```

- [ ] **Step 4: Write the smoke test**

Create `frontend/src/test/server.test.ts`:

```ts
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "./server";

describe("msw test server", () => {
  it("intercepts fetch and returns the default config handler", async () => {
    const response = await fetch("/config.json");
    const body = await response.json();

    expect(body.personas.map((p: { label: string }) => p.label)).toEqual([
      "Organizer",
      "Scorekeeper",
      "Player",
    ]);
  });

  it("lets a test override a handler for one request", async () => {
    server.use(http.get("/events", () => HttpResponse.json([{ id: "1", date: "2026-08-01" }])));

    const response = await fetch("/events");

    expect(await response.json()).toEqual([{ id: "1", date: "2026-08-01" }]);
  });
});
```

- [ ] **Step 5: Run the test suite and confirm the new tests pass and nothing else broke**

Run: `cd frontend && npm test -- --run`
Expected: all test files pass, including the two new `server.test.ts` cases and the pre-existing `App.test.tsx`/`ConfigProvider.test.tsx`/`AuthContext.test.tsx` (their manual `fetch` stubs still work — `vi.stubGlobal` replaces the global reference for that test regardless of msw's interceptor).

- [ ] **Step 6: Log the dependency decision**

Append to `DECISIONS.md`:

```markdown
## 2026-08-04 — Phase 7 PR2: msw for frontend component tests

Component tests for the Event/Pod/Entry setup screens mock HTTP at the
network layer via `msw` (`frontend/src/test/server.ts`) rather than
stubbing `AuthContext`'s `apiFetch` internals — tests exercise real
request/response shapes (URL, method, JSON body) the way the browser
actually sends them. Confirmed with the owner 2026-08-04, flagged in the
Phase 7 PR2 design spec's "New dependency" section.
```

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/test/server.ts frontend/src/test/server.test.ts frontend/src/test/setup.ts DECISIONS.md
git commit -m "test(frontend): add msw test server for network-layer mocking"
```

---

### Task 2: `apiRequest` helper

**Files:**
- Create: `frontend/src/api/request.ts`
- Test: `frontend/src/api/request.test.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `ApiFetch` (type alias `(path: string, init?: RequestInit) => Promise<Response>` — matches `AuthContext`'s `apiFetch` signature), `ApiError` (class, `.status: number`, `.message: string` = backend `detail`), `apiRequest<T>(apiFetch: ApiFetch, path: string, init?: RequestInit): Promise<T>`, `jsonInit(method: string, body: unknown): RequestInit`. All four are imported by every `src/api/*.ts` module in Tasks 3–5.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/api/request.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";
import { apiRequest, ApiError, jsonInit } from "./request";

function fetchReturning(response: { ok: boolean; status: number; statusText?: string; json?: () => Promise<unknown> }) {
  return vi.fn().mockResolvedValue(response);
}

describe("apiRequest", () => {
  it("parses a successful JSON response", async () => {
    const apiFetch = fetchReturning({ ok: true, status: 200, json: () => Promise.resolve({ id: "1" }) });

    const result = await apiRequest(apiFetch, "/events");

    expect(result).toEqual({ id: "1" });
    expect(apiFetch).toHaveBeenCalledWith("/events", undefined);
  });

  it("returns undefined for a 204 No Content response", async () => {
    const apiFetch = fetchReturning({ ok: true, status: 204 });

    const result = await apiRequest(apiFetch, "/entries/1", { method: "DELETE" });

    expect(result).toBeUndefined();
  });

  it("throws ApiError with the backend detail on a non-2xx response", async () => {
    const apiFetch = fetchReturning({
      ok: false,
      status: 422,
      statusText: "Unprocessable Entity",
      json: () => Promise.resolve({ detail: "date is required" }),
    });

    await expect(apiRequest(apiFetch, "/events", jsonInit("POST", {}))).rejects.toMatchObject({
      status: 422,
      message: "date is required",
    });
  });

  it("falls back to statusText when the error body isn't JSON", async () => {
    const apiFetch = fetchReturning({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.reject(new Error("not json")),
    });

    await expect(apiRequest(apiFetch, "/events")).rejects.toMatchObject({
      status: 500,
      message: "Internal Server Error",
    });
  });

  it("ApiError instances are real Errors", async () => {
    const apiFetch = fetchReturning({ ok: false, status: 404, statusText: "Not Found" });

    await expect(apiRequest(apiFetch, "/events/1")).rejects.toBeInstanceOf(ApiError);
    await expect(apiRequest(apiFetch, "/events/1")).rejects.toBeInstanceOf(Error);
  });
});

describe("jsonInit", () => {
  it("builds a JSON request init", () => {
    expect(jsonInit("POST", { date: "2026-08-01" })).toEqual({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: "2026-08-01" }),
    });
  });
});
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `cd frontend && npx vitest run src/api/request.test.ts`
Expected: FAIL — `Cannot find module './request'`

- [ ] **Step 3: Write the implementation**

Create `frontend/src/api/request.ts`:

```ts
export type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;

export class ApiError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiRequest<T>(apiFetch: ApiFetch, path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init);

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // response body wasn't JSON; fall back to statusText
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `cd frontend && npx vitest run src/api/request.test.ts`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/request.ts frontend/src/api/request.test.ts
git commit -m "feat(frontend): add apiRequest/ApiError/jsonInit http helpers"
```

---

### Task 3: Events API module

**Files:**
- Create: `frontend/src/api/events.ts`
- Test: `frontend/src/api/events.test.ts`

**Interfaces:**
- Consumes: `apiRequest`, `jsonInit`, `ApiFetch` from `frontend/src/api/request.ts` (Task 2).
- Produces: `EventRead { id: string; date: string }`, `listEvents(apiFetch): Promise<EventRead[]>`, `getEvent(apiFetch, eventId: string): Promise<EventRead>`, `createEvent(apiFetch, date: string): Promise<EventRead>` — consumed by `EventList` (Task 7), `NewEvent` (Task 8), `EventDetail` (Task 10).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/api/events.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";
import { createEvent, getEvent, listEvents } from "./events";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

describe("events api", () => {
  it("listEvents GETs /events", async () => {
    const apiFetch = fetchReturning([{ id: "1", date: "2026-08-01" }]);

    expect(await listEvents(apiFetch)).toEqual([{ id: "1", date: "2026-08-01" }]);
    expect(apiFetch).toHaveBeenCalledWith("/events", undefined);
  });

  it("getEvent GETs /events/:id", async () => {
    const apiFetch = fetchReturning({ id: "1", date: "2026-08-01" });

    expect(await getEvent(apiFetch, "1")).toEqual({ id: "1", date: "2026-08-01" });
    expect(apiFetch).toHaveBeenCalledWith("/events/1", undefined);
  });

  it("createEvent POSTs the date", async () => {
    const apiFetch = fetchReturning({ id: "1", date: "2026-08-01" }, 201);

    expect(await createEvent(apiFetch, "2026-08-01")).toEqual({ id: "1", date: "2026-08-01" });
    expect(apiFetch).toHaveBeenCalledWith("/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: "2026-08-01" }),
    });
  });
});
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `cd frontend && npx vitest run src/api/events.test.ts`
Expected: FAIL — `Cannot find module './events'`

- [ ] **Step 3: Write the implementation**

Create `frontend/src/api/events.ts`:

```ts
import { apiRequest, jsonInit, type ApiFetch } from "./request";

export interface EventRead {
  id: string;
  date: string;
}

export function listEvents(apiFetch: ApiFetch): Promise<EventRead[]> {
  return apiRequest(apiFetch, "/events");
}

export function getEvent(apiFetch: ApiFetch, eventId: string): Promise<EventRead> {
  return apiRequest(apiFetch, `/events/${eventId}`);
}

export function createEvent(apiFetch: ApiFetch, date: string): Promise<EventRead> {
  return apiRequest(apiFetch, "/events", jsonInit("POST", { date }));
}
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `cd frontend && npx vitest run src/api/events.test.ts`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/events.ts frontend/src/api/events.test.ts
git commit -m "feat(frontend): add events api helpers"
```

---

### Task 4: Pods API module

**Files:**
- Create: `frontend/src/api/pods.ts`
- Test: `frontend/src/api/pods.test.ts`

**Interfaces:**
- Consumes: `apiRequest`, `jsonInit`, `ApiFetch` from `frontend/src/api/request.ts` (Task 2).
- Produces: `PodRead { id: string; event_id: string; format_slug: string; game_slug: string; completed_at: string | null }`, `listPodsForEvent(apiFetch, eventId: string): Promise<PodRead[]>`, `createPod(apiFetch, eventId: string): Promise<PodRead>` — consumed by `EventDetail` (Task 10).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/api/pods.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";
import { createPod, listPodsForEvent } from "./pods";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

describe("pods api", () => {
  it("listPodsForEvent GETs /pods?event_id=", async () => {
    const apiFetch = fetchReturning([
      { id: "p1", event_id: "e1", format_slug: "swiss", game_slug: "generic", completed_at: null },
    ]);

    const pods = await listPodsForEvent(apiFetch, "e1");

    expect(pods).toEqual([
      { id: "p1", event_id: "e1", format_slug: "swiss", game_slug: "generic", completed_at: null },
    ]);
    expect(apiFetch).toHaveBeenCalledWith("/pods?event_id=e1", undefined);
  });

  it("createPod POSTs the fixed swiss/generic slugs", async () => {
    const apiFetch = fetchReturning(
      { id: "p1", event_id: "e1", format_slug: "swiss", game_slug: "generic", completed_at: null },
      201,
    );

    await createPod(apiFetch, "e1");

    expect(apiFetch).toHaveBeenCalledWith("/pods", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_id: "e1", format_slug: "swiss", game_slug: "generic" }),
    });
  });
});
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `cd frontend && npx vitest run src/api/pods.test.ts`
Expected: FAIL — `Cannot find module './pods'`

- [ ] **Step 3: Write the implementation**

Create `frontend/src/api/pods.ts`:

```ts
import { apiRequest, jsonInit, type ApiFetch } from "./request";

export interface PodRead {
  id: string;
  event_id: string;
  format_slug: string;
  game_slug: string;
  completed_at: string | null;
}

export function listPodsForEvent(apiFetch: ApiFetch, eventId: string): Promise<PodRead[]> {
  return apiRequest(apiFetch, `/pods?event_id=${eventId}`);
}

export function createPod(apiFetch: ApiFetch, eventId: string): Promise<PodRead> {
  return apiRequest(
    apiFetch,
    "/pods",
    jsonInit("POST", { event_id: eventId, format_slug: "swiss", game_slug: "generic" }),
  );
}
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `cd frontend && npx vitest run src/api/pods.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/pods.ts frontend/src/api/pods.test.ts
git commit -m "feat(frontend): add pods api helpers"
```

---

### Task 5: Entries API module

**Files:**
- Create: `frontend/src/api/entries.ts`
- Test: `frontend/src/api/entries.test.ts`

**Interfaces:**
- Consumes: `apiRequest`, `jsonInit`, `ApiFetch` from `frontend/src/api/request.ts` (Task 2).
- Produces: `EntryRead { id: string; pod_id: string; player_uuid: string; source_system: string; metadata: { display_name?: string; [key: string]: unknown } }`, `listEntries(apiFetch, podId: string): Promise<EntryRead[]>`, `createEntry(apiFetch, podId: string, displayName: string): Promise<EntryRead>`, `updateEntryDisplayName(apiFetch, entryId: string, displayName: string): Promise<EntryRead>`, `deleteEntry(apiFetch, entryId: string): Promise<void>` — consumed by `EntryRoster` (Task 9).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/api/entries.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";
import { createEntry, deleteEntry, listEntries, updateEntryDisplayName } from "./entries";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

describe("entries api", () => {
  it("listEntries GETs /entries?pod_id=", async () => {
    const apiFetch = fetchReturning([]);

    await listEntries(apiFetch, "pod-1");

    expect(apiFetch).toHaveBeenCalledWith("/entries?pod_id=pod-1", undefined);
  });

  it("createEntry generates a UUID and a fixed walk-in source_system", async () => {
    vi.spyOn(crypto, "randomUUID").mockReturnValue("11111111-1111-4111-8111-111111111111");
    const apiFetch = fetchReturning({ id: "e1" }, 201);

    await createEntry(apiFetch, "pod-1", "Ash");

    expect(apiFetch).toHaveBeenCalledWith("/entries", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pod_id: "pod-1",
        player_uuid: "11111111-1111-4111-8111-111111111111",
        source_system: "opentourney-ui",
        metadata: { display_name: "Ash" },
      }),
    });
  });

  it("updateEntryDisplayName PATCHes only metadata.display_name", async () => {
    const apiFetch = fetchReturning({ id: "e1" });

    await updateEntryDisplayName(apiFetch, "e1", "Misty");

    expect(apiFetch).toHaveBeenCalledWith("/entries/e1", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ metadata: { display_name: "Misty" } }),
    });
  });

  it("deleteEntry DELETEs /entries/:id", async () => {
    const apiFetch = vi.fn().mockResolvedValue({ ok: true, status: 204 });

    await deleteEntry(apiFetch, "e1");

    expect(apiFetch).toHaveBeenCalledWith("/entries/e1", { method: "DELETE" });
  });
});
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `cd frontend && npx vitest run src/api/entries.test.ts`
Expected: FAIL — `Cannot find module './entries'`

- [ ] **Step 3: Write the implementation**

Create `frontend/src/api/entries.ts`:

```ts
import { apiRequest, jsonInit, type ApiFetch } from "./request";

export interface EntryRead {
  id: string;
  pod_id: string;
  player_uuid: string;
  source_system: string;
  metadata: { display_name?: string; [key: string]: unknown };
}

const WALK_IN_SOURCE_SYSTEM = "opentourney-ui";

export function listEntries(apiFetch: ApiFetch, podId: string): Promise<EntryRead[]> {
  return apiRequest(apiFetch, `/entries?pod_id=${podId}`);
}

export function createEntry(apiFetch: ApiFetch, podId: string, displayName: string): Promise<EntryRead> {
  return apiRequest(
    apiFetch,
    "/entries",
    jsonInit("POST", {
      pod_id: podId,
      player_uuid: crypto.randomUUID(),
      source_system: WALK_IN_SOURCE_SYSTEM,
      metadata: { display_name: displayName },
    }),
  );
}

export function updateEntryDisplayName(
  apiFetch: ApiFetch,
  entryId: string,
  displayName: string,
): Promise<EntryRead> {
  return apiRequest(
    apiFetch,
    `/entries/${entryId}`,
    jsonInit("PATCH", { metadata: { display_name: displayName } }),
  );
}

export function deleteEntry(apiFetch: ApiFetch, entryId: string): Promise<void> {
  return apiRequest(apiFetch, `/entries/${entryId}`, { method: "DELETE" });
}
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `cd frontend && npx vitest run src/api/entries.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/entries.ts frontend/src/api/entries.test.ts
git commit -m "feat(frontend): add entries api helpers"
```

---

### Task 6: ErrorBanner component

**Files:**
- Create: `frontend/src/components/ErrorBanner.tsx`
- Test: `frontend/src/components/ErrorBanner.test.tsx`

**Interfaces:**
- Consumes: nothing.
- Produces: `ErrorBanner({ error: unknown })` — a React component. Consumed by `EventList` (Task 7), `NewEvent` (Task 8), `EntryRoster` (Task 9), `EventDetail` (Task 10).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/ErrorBanner.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ErrorBanner } from "./ErrorBanner";

describe("ErrorBanner", () => {
  it("renders nothing when there is no error", () => {
    const { container } = render(<ErrorBanner error={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders an Error's message", () => {
    render(<ErrorBanner error={new Error("date is required")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("date is required");
  });

  it("falls back to a generic message for a non-Error thrown value", () => {
    render(<ErrorBanner error="boom" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
  });
});
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `cd frontend && npx vitest run src/components/ErrorBanner.test.tsx`
Expected: FAIL — `Cannot find module './ErrorBanner'`

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/ErrorBanner.tsx`:

```tsx
export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;

  const message = error instanceof Error ? error.message : "Something went wrong.";

  return (
    <div
      role="alert"
      className="mb-4 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700"
    >
      {message}
    </div>
  );
}
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `cd frontend && npx vitest run src/components/ErrorBanner.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ErrorBanner.tsx frontend/src/components/ErrorBanner.test.tsx
git commit -m "feat(frontend): add ErrorBanner component"
```

---

### Task 7: EventList screen + test render helper + router wiring

**Files:**
- Create: `frontend/src/test/renderWithProviders.tsx`
- Create: `frontend/src/routes/EventList.tsx`
- Test: `frontend/src/routes/EventList.test.tsx`
- Modify: `frontend/src/routes/router.tsx`

**Interfaces:**
- Consumes: `listEvents`, `EventRead` (Task 3); `ErrorBanner` (Task 6); `useAuth` (existing, PR1's `AuthContext.tsx`); `server` (Task 1, in the test).
- Produces: `renderWithProviders(element: ReactElement, options?: { path?: string; routePath?: string; personaLabel?: string }): RenderResult` — wraps `element` in `QueryClientProvider`/`ConfigProvider`/`AuthProvider`/a memory router with a `*` fallback route rendering the current pathname in a `data-testid="navigated-to"` element (so tests can assert client-side navigation). `options.personaLabel` pre-seeds `localStorage["opentourney.persona"]` before render, matching `AuthContext`'s `STORAGE_KEY`. Consumed by every remaining component test in Tasks 8–10. Also produces `EventList` component, routed at `/`.

- [ ] **Step 1: Write the test render helper**

Create `frontend/src/test/renderWithProviders.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";
import { AuthProvider } from "../auth/AuthContext";
import { ConfigProvider } from "../config/ConfigProvider";

function NavigatedTo() {
  const location = useLocation();
  return <div data-testid="navigated-to">{location.pathname}</div>;
}

export function renderWithProviders(
  element: ReactElement,
  options: { path?: string; routePath?: string; personaLabel?: string } = {},
) {
  if (options.personaLabel) {
    localStorage.setItem("opentourney.persona", options.personaLabel);
  }

  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  const path = options.path ?? "/";
  const routePath = options.routePath ?? path;
  const router = createMemoryRouter(
    [
      { path: routePath, element },
      { path: "*", element: <NavigatedTo /> },
    ],
    { initialEntries: [path] },
  );

  return render(
    <QueryClientProvider client={queryClient}>
      <ConfigProvider>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </ConfigProvider>
    </QueryClientProvider>,
  );
}
```

This has no test of its own — it's exercised indirectly by every screen test below (per Task Right-Sizing: a helper isn't an independent deliverable).

- [ ] **Step 2: Write the failing EventList tests**

Create `frontend/src/routes/EventList.test.tsx`:

```tsx
import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { EventList } from "./EventList";

describe("EventList", () => {
  beforeEach(() => localStorage.clear());

  it("renders events as links to their detail page", async () => {
    server.use(
      http.get("/events", () =>
        HttpResponse.json([
          { id: "1", date: "2026-08-01" },
          { id: "2", date: "2026-09-01" },
        ]),
      ),
    );

    renderWithProviders(<EventList />);

    expect(await screen.findByRole("link", { name: "2026-08-01" })).toHaveAttribute("href", "/events/1");
    expect(screen.getByRole("link", { name: "2026-09-01" })).toHaveAttribute("href", "/events/2");
  });

  it("shows New Event only for the Organizer persona", async () => {
    server.use(http.get("/events", () => HttpResponse.json([])));

    renderWithProviders(<EventList />, { personaLabel: "Scorekeeper" });

    await screen.findByText("No events yet.");
    expect(screen.queryByRole("link", { name: "New Event" })).not.toBeInTheDocument();
  });

  it("surfaces a fetch error via ErrorBanner", async () => {
    server.use(http.get("/events", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));

    renderWithProviders(<EventList />);

    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });
});
```

- [ ] **Step 3: Run the tests and verify they fail**

Run: `cd frontend && npx vitest run src/routes/EventList.test.tsx`
Expected: FAIL — `Cannot find module './EventList'`

- [ ] **Step 4: Write the implementation**

Create `frontend/src/routes/EventList.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { listEvents } from "../api/events";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

export function EventList() {
  const { apiFetch, currentPersona } = useAuth();
  const {
    data: events,
    error,
    isLoading,
  } = useQuery({ queryKey: ["events"], queryFn: () => listEvents(apiFetch) });

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Events</h2>
        {currentPersona.role === "organizer" && (
          <Link to="/events/new" className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white">
            New Event
          </Link>
        )}
      </div>
      <ErrorBanner error={error} />
      {isLoading && <p>Loading…</p>}
      {events && events.length === 0 && <p>No events yet.</p>}
      {events && events.length > 0 && (
        <ul className="divide-y divide-gray-200">
          {events.map((event) => (
            <li key={event.id} className="py-2">
              <Link to={`/events/${event.id}`} className="text-blue-700 hover:underline">
                {event.date}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Wire EventList into the router**

Modify `frontend/src/routes/router.tsx`:

```tsx
import { createBrowserRouter } from "react-router";
import { EventList } from "./EventList";
import { Layout } from "./Layout";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <EventList /> },
      { path: "events/new", element: <div>New Event</div> },
      { path: "events/:eventId", element: <div>Event Detail</div> },
      { path: "pods/:podId/pairings", element: <div>Pairings</div> },
      { path: "pods/:podId/report", element: <div>Report</div> },
    ],
  },
]);
```

- [ ] **Step 6: Run the tests and verify they pass**

Run: `cd frontend && npx vitest run src/routes/EventList.test.tsx`
Expected: PASS (3 tests)

Also run the full suite to confirm `App.test.tsx` (which asserts `screen.getByText("Events")` for the index route) still passes now that the index route renders a real component instead of `<div>Events</div>`:

Run: `cd frontend && npm test -- --run`
Expected: PASS — `App.test.tsx`'s Organizer-default render shows the "Events" `<h2>` from `EventList`, and no "New Event" fetch is needed since `App.test.tsx` only asserts the heading text, not the link.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/test/renderWithProviders.tsx frontend/src/routes/EventList.tsx frontend/src/routes/EventList.test.tsx frontend/src/routes/router.tsx
git commit -m "feat(frontend): add EventList screen"
```

---

### Task 8: NewEvent screen + router wiring

**Files:**
- Create: `frontend/src/routes/NewEvent.tsx`
- Test: `frontend/src/routes/NewEvent.test.tsx`
- Modify: `frontend/src/routes/router.tsx`

**Interfaces:**
- Consumes: `createEvent`, `EventRead` (Task 3); `ErrorBanner` (Task 6); `renderWithProviders` (Task 7).
- Produces: `NewEvent` component, routed at `/events/new`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/routes/NewEvent.test.tsx`:

```tsx
import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { NewEvent } from "./NewEvent";

describe("NewEvent", () => {
  beforeEach(() => localStorage.clear());

  it("creates an event and navigates to its detail page", async () => {
    server.use(
      http.post("/events", async ({ request }) => {
        const body = (await request.json()) as { date: string };
        return HttpResponse.json({ id: "new-1", date: body.date }, { status: 201 });
      }),
    );

    renderWithProviders(<NewEvent />, { path: "/events/new" });

    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2026-08-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Event" }));

    expect(await screen.findByTestId("navigated-to")).toHaveTextContent("/events/new-1");
  });

  it("surfaces a validation error from the backend", async () => {
    server.use(
      http.post("/events", () => HttpResponse.json({ detail: "date is required" }, { status: 422 })),
    );

    renderWithProviders(<NewEvent />, { path: "/events/new" });

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

- [ ] **Step 2: Run the tests and verify they fail**

Run: `cd frontend && npx vitest run src/routes/NewEvent.test.tsx`
Expected: FAIL — `Cannot find module './NewEvent'`

- [ ] **Step 3: Write the implementation**

Create `frontend/src/routes/NewEvent.tsx`:

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router";
import { createEvent } from "../api/events";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

export function NewEvent() {
  const { apiFetch, currentPersona } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [date, setDate] = useState("");

  const mutation = useMutation({
    mutationFn: () => createEvent(apiFetch, date),
    onSuccess: (event) => {
      queryClient.invalidateQueries({ queryKey: ["events"] });
      navigate(`/events/${event.id}`);
    },
  });

  if (currentPersona.role !== "organizer") {
    return <Navigate to="/" replace />;
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        mutation.mutate();
      }}
    >
      <h2 className="mb-4 text-lg font-semibold">New Event</h2>
      <ErrorBanner error={mutation.error} />
      <label className="block text-sm">
        Date
        <input
          type="date"
          required
          value={date}
          onChange={(event) => setDate(event.target.value)}
          className="mt-1 block rounded border border-gray-300 px-2 py-1"
        />
      </label>
      <button
        type="submit"
        disabled={mutation.isPending}
        className="mt-4 rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
      >
        Create Event
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Wire NewEvent into the router**

Modify `frontend/src/routes/router.tsx` — replace the `events/new` line:

```tsx
      { path: "events/new", element: <NewEvent /> },
```

Add the import alongside the `EventList` import:

```tsx
import { NewEvent } from "./NewEvent";
```

- [ ] **Step 5: Run the tests and verify they pass**

Run: `cd frontend && npx vitest run src/routes/NewEvent.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/NewEvent.tsx frontend/src/routes/NewEvent.test.tsx frontend/src/routes/router.tsx
git commit -m "feat(frontend): add NewEvent screen"
```

---

### Task 9: EntryRoster component

**Files:**
- Create: `frontend/src/routes/EntryRoster.tsx`
- Test: `frontend/src/routes/EntryRoster.test.tsx`

**Interfaces:**
- Consumes: `listEntries`, `createEntry`, `updateEntryDisplayName`, `deleteEntry`, `EntryRead` (Task 5); `ErrorBanner` (Task 6); `renderWithProviders` (Task 7).
- Produces: `EntryRoster({ podId: string })` — consumed by `EventDetail` (Task 10).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/routes/EntryRoster.test.tsx`:

```tsx
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { EntryRoster } from "./EntryRoster";

const ASH = {
  id: "e1",
  pod_id: "pod-1",
  player_uuid: "u1",
  source_system: "opentourney-ui",
  metadata: { display_name: "Ash" },
};

describe("EntryRoster", () => {
  beforeEach(() => localStorage.clear());

  it("lists entries by display name", async () => {
    server.use(http.get("/entries", () => HttpResponse.json([ASH])));

    renderWithProviders(<EntryRoster podId="pod-1" />);

    expect(await screen.findByText("Ash")).toBeInTheDocument();
  });

  it("adds an entry as Organizer", async () => {
    // Stateful handler: the component invalidates and refetches GET /entries
    // after the mutation, so a static handler would mask a broken add by
    // just re-serving the original (empty) list.
    let entries: (typeof ASH)[] = [];
    server.use(
      http.get("/entries", () => HttpResponse.json(entries)),
      http.post("/entries", async ({ request }) => {
        const body = (await request.json()) as { metadata: { display_name: string } };
        const created = { ...ASH, metadata: body.metadata };
        entries = [created];
        return HttpResponse.json(created, { status: 201 });
      }),
    );

    renderWithProviders(<EntryRoster podId="pod-1" />);
    await screen.findByText("No entries yet.");

    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Ash" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Entry" }));

    expect(await screen.findByText("Ash")).toBeInTheDocument();
  });

  it("edits an entry's display name", async () => {
    // Stateful handler for the same reason as the add-entry test above.
    let current = ASH;
    server.use(
      http.get("/entries", () => HttpResponse.json([current])),
      http.patch("/entries/e1", async ({ request }) => {
        const body = (await request.json()) as { metadata: { display_name: string } };
        current = { ...current, metadata: body.metadata };
        return HttpResponse.json(current);
      }),
    );

    renderWithProviders(<EntryRoster podId="pod-1" />);
    await screen.findByText("Ash");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Edit name for Ash"), { target: { value: "Misty" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Misty")).toBeInTheDocument();
  });

  it("deletes an entry", async () => {
    let deleted = false;
    server.use(
      http.get("/entries", () => HttpResponse.json(deleted ? [] : [ASH])),
      http.delete("/entries/e1", () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderWithProviders(<EntryRoster podId="pod-1" />);
    await screen.findByText("Ash");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(screen.queryByText("Ash")).not.toBeInTheDocument());
  });

  it("hides mutation controls for a non-Organizer persona", async () => {
    server.use(http.get("/entries", () => HttpResponse.json([ASH])));

    renderWithProviders(<EntryRoster podId="pod-1" />, { personaLabel: "Player" });

    await screen.findByText("Ash");
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Display name")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `cd frontend && npx vitest run src/routes/EntryRoster.test.tsx`
Expected: FAIL — `Cannot find module './EntryRoster'`

- [ ] **Step 3: Write the implementation**

Create `frontend/src/routes/EntryRoster.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createEntry, deleteEntry, listEntries, updateEntryDisplayName, type EntryRead } from "../api/entries";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

export function EntryRoster({ podId }: { podId: string }) {
  const { apiFetch, currentPersona } = useAuth();
  const queryClient = useQueryClient();
  const isOrganizer = currentPersona.role === "organizer";

  const {
    data: entries,
    error,
    isLoading,
  } = useQuery({ queryKey: ["entries", podId], queryFn: () => listEntries(apiFetch, podId) });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["entries", podId] });

  const createMutation = useMutation({
    mutationFn: (displayName: string) => createEntry(apiFetch, podId, displayName),
    onSuccess: invalidate,
  });
  const updateMutation = useMutation({
    mutationFn: (args: { entryId: string; displayName: string }) =>
      updateEntryDisplayName(apiFetch, args.entryId, args.displayName),
    onSuccess: invalidate,
  });
  const deleteMutation = useMutation({
    mutationFn: (entryId: string) => deleteEntry(apiFetch, entryId),
    onSuccess: invalidate,
  });

  const [newName, setNewName] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");

  return (
    <div>
      <h3 className="mb-2 font-semibold">Entries</h3>
      <ErrorBanner error={createMutation.error ?? updateMutation.error ?? deleteMutation.error ?? error} />
      {isLoading && <p>Loading…</p>}
      {entries && entries.length === 0 && <p>No entries yet.</p>}
      {entries && entries.length > 0 && (
        <ul className="mb-4 divide-y divide-gray-200">
          {entries.map((entry: EntryRead) =>
            editingId === entry.id ? (
              <li key={entry.id} className="flex items-center gap-2 py-2">
                <input
                  aria-label={`Edit name for ${entry.metadata.display_name ?? entry.id}`}
                  value={editingName}
                  onChange={(event) => setEditingName(event.target.value)}
                  className="rounded border border-gray-300 px-2 py-1"
                />
                <button
                  onClick={() => {
                    updateMutation.mutate({ entryId: entry.id, displayName: editingName });
                    setEditingId(null);
                  }}
                >
                  Save
                </button>
                <button onClick={() => setEditingId(null)}>Cancel</button>
              </li>
            ) : (
              <li key={entry.id} className="flex items-center justify-between py-2">
                <span>{entry.metadata.display_name ?? "(unnamed)"}</span>
                {isOrganizer && (
                  <span className="flex gap-2">
                    <button
                      onClick={() => {
                        setEditingId(entry.id);
                        setEditingName(entry.metadata.display_name ?? "");
                      }}
                    >
                      Edit
                    </button>
                    <button onClick={() => deleteMutation.mutate(entry.id)}>Delete</button>
                  </span>
                )}
              </li>
            ),
          )}
        </ul>
      )}
      {isOrganizer && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            createMutation.mutate(newName);
            setNewName("");
          }}
          className="flex gap-2"
        >
          <label className="flex items-center gap-2 text-sm">
            Display name
            <input
              required
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              className="rounded border border-gray-300 px-2 py-1"
            />
          </label>
          <button type="submit" className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white">
            Add Entry
          </button>
        </form>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `cd frontend && npx vitest run src/routes/EntryRoster.test.tsx`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/EntryRoster.tsx frontend/src/routes/EntryRoster.test.tsx
git commit -m "feat(frontend): add EntryRoster component"
```

---

### Task 10: EventDetail screen + router wiring

**Files:**
- Create: `frontend/src/routes/EventDetail.tsx`
- Test: `frontend/src/routes/EventDetail.test.tsx`
- Modify: `frontend/src/routes/router.tsx`

**Interfaces:**
- Consumes: `getEvent` (Task 3); `createPod`, `listPodsForEvent`, `PodRead` (Task 4); `EntryRoster` (Task 9); `ErrorBanner` (Task 6); `renderWithProviders` (Task 7).
- Produces: `EventDetail` component, routed at `/events/:eventId`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/routes/EventDetail.test.tsx`:

```tsx
import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { EventDetail } from "./EventDetail";

const EVENT = { id: "event-1", date: "2026-08-01" };
const POD = { id: "pod-1", event_id: "event-1", format_slug: "swiss", game_slug: "generic", completed_at: null };

function renderDetail(personaLabel?: string) {
  renderWithProviders(<EventDetail />, {
    path: "/events/event-1",
    routePath: "/events/:eventId",
    personaLabel,
  });
}

describe("EventDetail", () => {
  beforeEach(() => localStorage.clear());

  it("shows a Create Pod action when the event has no pod", async () => {
    server.use(
      http.get("/events/event-1", () => HttpResponse.json(EVENT)),
      http.get("/pods", () => HttpResponse.json([])),
    );

    renderDetail();

    expect(await screen.findByText("This event has no pod yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create Pod" })).toBeInTheDocument();
  });

  it("creates a pod with the default format/game slugs and then shows the roster", async () => {
    server.use(
      http.get("/events/event-1", () => HttpResponse.json(EVENT)),
      http.get("/pods", () => HttpResponse.json([])),
      http.post("/pods", async ({ request }) => {
        const body = await request.json();
        expect(body).toEqual({ event_id: "event-1", format_slug: "swiss", game_slug: "generic" });
        return HttpResponse.json(POD, { status: 201 });
      }),
      http.get("/entries", () => HttpResponse.json([])),
    );

    renderDetail();
    fireEvent.click(await screen.findByRole("button", { name: "Create Pod" }));

    expect(await screen.findByText("No entries yet.")).toBeInTheDocument();
  });

  it("renders the entry roster once a pod exists", async () => {
    server.use(
      http.get("/events/event-1", () => HttpResponse.json(EVENT)),
      http.get("/pods", () => HttpResponse.json([POD])),
      http.get("/entries", () =>
        HttpResponse.json([
          { id: "e1", pod_id: "pod-1", player_uuid: "u1", source_system: "opentourney-ui", metadata: { display_name: "Ash" } },
        ]),
      ),
    );

    renderDetail();

    expect(await screen.findByText("Ash")).toBeInTheDocument();
  });

  it("hides Create Pod for a non-Organizer persona", async () => {
    server.use(
      http.get("/events/event-1", () => HttpResponse.json(EVENT)),
      http.get("/pods", () => HttpResponse.json([])),
    );

    renderDetail("Player");

    await screen.findByText("This event has no pod yet.");
    expect(screen.queryByRole("button", { name: "Create Pod" })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `cd frontend && npx vitest run src/routes/EventDetail.test.tsx`
Expected: FAIL — `Cannot find module './EventDetail'`

- [ ] **Step 3: Write the implementation**

Create `frontend/src/routes/EventDetail.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router";
import { getEvent } from "../api/events";
import { createPod, listPodsForEvent } from "../api/pods";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";
import { EntryRoster } from "./EntryRoster";

export function EventDetail() {
  const { eventId } = useParams<{ eventId: string }>();
  if (!eventId) throw new Error("EventDetail rendered without an eventId route param");

  const { apiFetch, currentPersona } = useAuth();
  const queryClient = useQueryClient();
  const isOrganizer = currentPersona.role === "organizer";

  const eventQuery = useQuery({ queryKey: ["events", eventId], queryFn: () => getEvent(apiFetch, eventId) });
  const podsQuery = useQuery({
    queryKey: ["pods", eventId],
    queryFn: () => listPodsForEvent(apiFetch, eventId),
  });

  const createPodMutation = useMutation({
    mutationFn: () => createPod(apiFetch, eventId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pods", eventId] }),
  });

  const pod = podsQuery.data?.[0];

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">Event {eventQuery.data ? eventQuery.data.date : "…"}</h2>
      <ErrorBanner error={eventQuery.error ?? podsQuery.error ?? createPodMutation.error} />

      {podsQuery.data && !pod && (
        <div className="mb-6">
          <p className="mb-2 text-sm text-gray-600">This event has no pod yet.</p>
          {isOrganizer && (
            <button
              onClick={() => createPodMutation.mutate()}
              disabled={createPodMutation.isPending}
              className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
            >
              Create Pod
            </button>
          )}
        </div>
      )}

      {pod && <EntryRoster podId={pod.id} />}
    </div>
  );
}
```

- [ ] **Step 4: Wire EventDetail into the router**

Modify `frontend/src/routes/router.tsx` — replace the `events/:eventId` line:

```tsx
      { path: "events/:eventId", element: <EventDetail /> },
```

Add the import alongside the others:

```tsx
import { EventDetail } from "./EventDetail";
```

- [ ] **Step 5: Run the tests and verify they pass**

Run: `cd frontend && npx vitest run src/routes/EventDetail.test.tsx`
Expected: PASS (4 tests)

Then run the whole frontend suite:

Run: `cd frontend && npm test -- --run`
Expected: all test files pass.

Then typecheck and lint:

Run: `cd frontend && npm run build && npm run lint`
Expected: both succeed with no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/EventDetail.tsx frontend/src/routes/EventDetail.test.tsx frontend/src/routes/router.tsx
git commit -m "feat(frontend): add EventDetail screen"
```

---

### Task 11: Backend integration flow test

**Files:**
- Create: `backend/tests/integration/test_setup_flow_api.py`

**Interfaces:**
- Consumes: existing fixtures `api_client`, `make_token`, `db_session` (`backend/tests/integration/conftest.py`); existing models `Entry`, `Pod` (`backend/app/models`).
- Produces: nothing consumed by other tasks — this is the acceptance-adjacent integration test required by Testing Layers for a boundary-crossing change.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_setup_flow_api.py`:

```python
import uuid

from app.models import Entry, Pod


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_organizer_setup_flow_create_event_pod_entries(api_client, make_token, db_session):
    """Mirrors the PR2 UI flow: create Event -> create Pod (default swiss/generic
    slugs, matching EventDetail's hidden auto-fill) -> add walk-in Entries
    (generated player_uuid, source_system="opentourney-ui", per EntryRoster)."""
    organizer_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    event_response = api_client.post(
        "/events", json={"date": "2026-08-01"}, headers=_auth_headers(organizer_token)
    )
    assert event_response.status_code == 201
    event_id = event_response.json()["id"]

    pod_response = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(organizer_token),
    )
    assert pod_response.status_code == 201
    pod_id = pod_response.json()["id"]

    entry_ids = []
    for display_name in ("Ash", "Misty"):
        entry_response = api_client.post(
            "/entries",
            json={
                "pod_id": pod_id,
                "player_uuid": str(uuid.uuid4()),
                "source_system": "opentourney-ui",
                "metadata": {"display_name": display_name},
            },
            headers=_auth_headers(organizer_token),
        )
        assert entry_response.status_code == 201
        entry_ids.append(entry_response.json()["id"])

    roster_response = api_client.get(
        "/entries", params={"pod_id": pod_id}, headers=_auth_headers(organizer_token)
    )
    assert roster_response.status_code == 200
    roster = roster_response.json()
    assert {row["id"] for row in roster} == set(entry_ids)
    assert {row["metadata"]["display_name"] for row in roster} == {"Ash", "Misty"}
    assert all(row["source_system"] == "opentourney-ui" for row in roster)

    persisted_entries = db_session.query(Entry).filter_by(pod_id=uuid.UUID(pod_id)).all()
    assert {str(entry.id) for entry in persisted_entries} == set(entry_ids)

    pod = db_session.get(Pod, uuid.UUID(pod_id))
    assert pod.format_slug == "swiss"
    assert pod.game_slug == "generic"
```

- [ ] **Step 2: Run the test and verify it fails for the right reason first (sanity check the fixtures are wired), then verify it passes**

Run: `cd backend && python -m pytest tests/integration/test_setup_flow_api.py -v`
Expected: PASS — this exercises already-shipped, already-tested endpoints, so the "RED" phase here is about catching a typo in the flow, not missing functionality. If it fails, read the failure: a 403 means the `make_token(roles=["organizer"])` shape or an RBAC dependency changed since Phase 6; a 404/422 means a request shape mismatch with the current schemas in `backend/app/schemas/`.

- [ ] **Step 3: Run the full backend test suite to confirm no regressions**

Run: `cd backend && python -m pytest -v`
Expected: all tests pass, including the new one.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_setup_flow_api.py
git commit -m "test(backend): add integration test for the event/pod/entry setup flow"
```

---

## Post-plan (not a task — handled by the PR workflow, not this plan)

- `git push` + `gh pr create` referencing FR19 and this plan
- `/review`, triage findings per CLAUDE.md
- Manual verification gate: bring the app up locally/staging, walk through Organizer create-event → create-pod → add-entries, and confirm Scorekeeper/Player personas see a read-only roster with no New Event / Create Pod / Add Entry / Edit / Delete controls
- Screenshot staging UI via Playwright before the PR per the standing frontend-phase convention
