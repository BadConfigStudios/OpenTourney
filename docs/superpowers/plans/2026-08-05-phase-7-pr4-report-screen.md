# Phase 7 PR4 — Report Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `/pods/:podId/report` standings screen (FR22), consuming
the existing `GET /pods/{id}/report` and `POST /pods/{id}/complete`
endpoints, and fix the SPA/backend route collision on that path (and the
pre-existing `/events/:eventId` one) with an Accept-header dispatch
mechanism that replaces PR3's regex carve-out.

**Architecture:** Two independent pieces. (1) Infra: `AuthContext.tsx`'s
`apiFetch` sends `Accept: application/json` on every request; `nginx.conf`
and `vite.config.ts` dispatch each backend-prefixed path to either the SPA
(`Accept: text/html`, i.e. real browser navigation) or the backend proxy
(anything else), replacing path-based carve-outs. (2) Feature: a new
`Report.tsx` screen fetches `PodReport` + entries, renders banners for
`is_partial`/`!is_complete`, a ranked standings table, and an
Organizer-only "Complete Pod" action — following the same
`useQuery`/`useMutation`/`<ErrorBanner>` pattern already used by
`Pairings.tsx` and `EventDetail.tsx`.

**Tech Stack:** React + TypeScript, `@tanstack/react-query`, `react-router`,
Tailwind v4, Vitest + Testing Library + `msw` (frontend); FastAPI +
pytest (backend integration test only — no backend code changes).

## Global Constraints

- No backend code changes — `POST /pods/{id}/complete` and
  `GET /pods/{id}/report` already exist and are unchanged.
- No new dependencies.
- Follow existing patterns exactly: `apiRequest`/`jsonInit` from
  `frontend/src/api/request.ts` for all API calls; `useQuery`/`useMutation`
  + `<ErrorBanner>` for screen data/error handling; `msw` `server.use(...)`
  per-test handlers for component tests (see `Pairings.test.tsx`,
  `EventDetail.test.tsx`).
- Commit after each task.

---

### Task 1: `Accept: application/json` on every API request

**Files:**
- Modify: `frontend/src/auth/AuthContext.tsx:45-49`
- Test: `frontend/src/auth/AuthContext.test.tsx`

**Interfaces:**
- Consumes: nothing new — `apiFetch`'s existing signature
  (`(path: string, init?: RequestInit) => Promise<Response>`) is unchanged,
  only its headers change.
- Produces: nothing new exported — this is a behavior-only change every
  later task (and every existing caller) picks up automatically.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/auth/AuthContext.test.tsx`, inside the existing
`describe("AuthProvider")` block, after the `"apiFetch attaches the
current persona's Bearer token"` test:

```tsx
  it("apiFetch sends an explicit Accept: application/json header", async () => {
    renderWithProviders();
    await screen.findByText("Organizer");
    const fetchSpy = vi.mocked(fetch);
    fetchSpy.mockClear();

    await act(async () => screen.getByText("fetch").click());

    expect(fetchSpy).toHaveBeenCalledWith(
      "/events",
      expect.objectContaining({ headers: expect.objectContaining({ Accept: "application/json" }) }),
    );
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/auth/AuthContext.test.tsx`
Expected: FAIL — the new test's `expect(fetchSpy).toHaveBeenCalledWith(...)`
assertion fails because no `Accept` header is currently sent.

- [ ] **Step 3: Implement**

In `frontend/src/auth/AuthContext.tsx`, change the `apiFetch` implementation:

```tsx
      apiFetch: (path: string, init: RequestInit = {}) =>
        fetch(path, {
          ...init,
          headers: {
            ...init.headers,
            Authorization: `Bearer ${currentPersona.token}`,
            Accept: "application/json",
          },
        }),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/auth/AuthContext.test.tsx`
Expected: PASS (both the existing Bearer-token test and the new one).

Run the full frontend suite to confirm nothing else broke:
Run: `cd frontend && npx vitest run`
Expected: PASS — no test asserted an exact `headers` object that would
now mismatch (existing assertions use `expect.objectContaining`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/auth/AuthContext.tsx frontend/src/auth/AuthContext.test.tsx
git commit -m "feat(frontend): send explicit Accept: application/json on every API request"
```

---

### Task 2: Accept-header route dispatch (nginx + Vite), replacing PR3's carve-out

**Files:**
- Modify: `frontend/nginx.conf`
- Modify: `frontend/vite.config.ts`
- Modify: `DEVELOPMENT.md:12-18`

**Interfaces:**
- Consumes: Task 1's `Accept: application/json` header (this is the signal
  the dispatch logic keys off).
- Produces: nothing consumed by later tasks — this is infra-only, verified
  manually (no TS/Python symbols).

- [ ] **Step 1: Rewrite `frontend/nginx.conf`**

Replace the full file with:

```nginx
map $http_accept $accepts_html {
    default 0;
    "~*text/html" 1;
}

server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # Backend API routes: proxy the real path prefixes to the backend Service
    # (Kubernetes Service "backend", see charts/opentourney/templates/service-backend.yaml,
    # listening on Values.backend.port, currently 8000). Authorization and other
    # headers are forwarded by proxy_pass by default; nothing here strips them.
    #
    # Some of these prefixes collide with SPA client-side routes at the exact
    # same path (/events/:eventId vs GET /events/{id}, /pods/:podId/report vs
    # GET /pods/{id}/report, /pods/:podId/pairings has no backend counterpart
    # but shares the /pods prefix). Real browser navigation (hard refresh,
    # direct link) sends "Accept: text/html,..."; the frontend's own apiFetch
    # sends "Accept: application/json" (see AuthContext.tsx). $accepts_html
    # (set by the map above) tells the two apart regardless of path, so a
    # single mechanism covers every current and future collision on these
    # prefixes.
    location /events {
        if ($accepts_html) {
            rewrite ^ /index.html break;
        }
        proxy_pass http://backend:8000;
    }

    location /pods {
        if ($accepts_html) {
            rewrite ^ /index.html break;
        }
        proxy_pass http://backend:8000;
    }

    location /entries {
        if ($accepts_html) {
            rewrite ^ /index.html break;
        }
        proxy_pass http://backend:8000;
    }

    location /matches {
        if ($accepts_html) {
            rewrite ^ /index.html break;
        }
        proxy_pass http://backend:8000;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 2: Verify nginx.conf syntax**

Run: `docker run --rm -v "$(pwd)/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:alpine nginx -t`
Expected: `nginx: configuration file /etc/nginx/nginx.conf test is successful`

This only checks syntax, not dispatch behavior — behavior is verified in
Step 6 below (Vite dev proxy, which shares the same Accept-header logic)
and again against staging during this PR's mandatory manual verification
gate (hard refresh on both collided routes).

- [ ] **Step 3: Rewrite `frontend/vite.config.ts`**

Replace the full file with:

```ts
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Real browser navigation (hard refresh, direct link) sends
// "Accept: text/html,..."; the frontend's own apiFetch sends
// "Accept: application/json" (see AuthContext.tsx). Some of these prefixes
// collide with SPA client-side routes at the exact same path
// (/events/:eventId, /pods/:podId/report) — checking Accept tells the two
// apart regardless of path, mirroring the nginx.conf dispatch used in prod.
function bypassOnHtmlAccept(req: { headers: { accept?: string }; url?: string }) {
  if (req.url && /text\/html/.test(req.headers.accept ?? "")) {
    return req.url;
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Proxy the backend's real path prefixes to the local dev backend
    // (see backend/Dockerfile.prod / uvicorn, which serves on :8000),
    // mirroring the prod nginx.conf proxy_pass blocks below.
    proxy: {
      "/events": { target: "http://localhost:8000", bypass: bypassOnHtmlAccept },
      "/pods": { target: "http://localhost:8000", bypass: bypassOnHtmlAccept },
      "/entries": { target: "http://localhost:8000", bypass: bypassOnHtmlAccept },
      "/matches": { target: "http://localhost:8000", bypass: bypassOnHtmlAccept },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    unstubGlobals: true,
    restoreMocks: true,
  },
});
```

- [ ] **Step 4: Run the frontend test suite (regression check)**

Run: `cd frontend && npx vitest run`
Expected: PASS — `vite.config.ts` changes don't affect Vitest's test
environment (`test` block untouched), only the dev-server proxy.

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS, no type errors from `bypassOnHtmlAccept`'s inline
parameter type.

- [ ] **Step 6: Manually verify the Vite dispatch**

In one terminal, start a stand-in backend on port 8000 (its exact
response doesn't matter — only that it's distinguishable from the SPA's
`index.html`):

Run: `python3 -m http.server 8000`

In a second terminal:

Run: `cd frontend && npm run dev`

In a third terminal:

Run: `curl -s http://localhost:5173/pods/test-id/report | head -c 200`
Expected: contains `Directory listing for` (Python's `http.server` index
page) — confirms a default `Accept: */*` request is proxied to the
backend, not served the SPA.

Run: `curl -s -H "Accept: text/html" http://localhost:5173/pods/test-id/report | head -c 200`
Expected: contains `<title>OpenTourney</title>` (the SPA's `index.html`)
— confirms a browser-style request is served the SPA instead of proxied.

Stop both the `http.server` and `npm run dev` processes (Ctrl-C in each
terminal) once both curl checks pass.

- [ ] **Step 7: Update `DEVELOPMENT.md`**

Replace the "Known limitation" sentence (currently lines 12-18) so the
paragraph reads:

```markdown
The frontend's dev server (`npm run dev`) and the prod nginx container both proxy
`/events`, `/pods`, `/entries`, and `/matches` to the backend (`http://localhost:8000`
in dev via `vite.config.ts`'s `server.proxy`, `http://backend:8000` in the cluster via
`nginx.conf`), since the backend mounts its routers directly under those prefixes with
no `/api` namespace. Several SPA client-side routes collide with backend routes at the
exact same path (`/events/:eventId` vs. `GET /events/{id}`, `/pods/:podId/report` vs.
`GET /pods/{id}/report`) — both nginx.conf and vite.config.ts resolve this by
dispatching on the `Accept` request header rather than the path: real browser
navigation (hard refresh, direct link) sends `Accept: text/html,...` and is served the
SPA, while the frontend's own API calls send `Accept: application/json` (see
`AuthContext.tsx`'s `apiFetch`) and are proxied to the backend. One edge case: a
non-browser HTTP client hitting either collided path without an explicit
`Accept: text/html` (e.g. plain `curl`) is routed to the backend, not the SPA — correct
behavior for an API consumer, just worth knowing if debugging a "why did I get JSON
instead of the app" report. A proper `/api` namespace on the backend would remove the
ambiguity entirely; that's out of scope here.
```

- [ ] **Step 8: Commit**

```bash
git add frontend/nginx.conf frontend/vite.config.ts DEVELOPMENT.md
git commit -m "fix(frontend): dispatch SPA vs backend on Accept header, not path

Replaces PR3's /pairings regex carve-out with a mechanism that also
covers the /pods/:podId/report and /events/:eventId collisions."
```

---

### Task 3: `report.ts` API module + `completePod`

**Files:**
- Create: `frontend/src/api/report.ts`
- Test: `frontend/src/api/report.test.ts`
- Modify: `frontend/src/api/pods.ts`
- Test: `frontend/src/api/pods.test.ts`

**Interfaces:**
- Consumes: `apiRequest`, `type ApiFetch` from `frontend/src/api/request.ts`
  (existing); `PodRead` from `frontend/src/api/pods.ts` (existing).
- Produces: `StandingRow { entry_id: string; points: number; rank: number }`,
  `PodReport { is_complete: boolean; rounds_played: number; is_partial: boolean; standings: StandingRow[] }`,
  `fetchPodReport(apiFetch: ApiFetch, podId: string): Promise<PodReport>`
  (all from `frontend/src/api/report.ts`); `completePod(apiFetch: ApiFetch, podId: string): Promise<PodRead>`
  (from `frontend/src/api/pods.ts`) — Task 4 imports all four.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/api/report.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";
import { fetchPodReport } from "./report";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

describe("report api", () => {
  it("fetchPodReport GETs /pods/:id/report", async () => {
    const apiFetch = fetchReturning({
      is_complete: false,
      rounds_played: 2,
      is_partial: true,
      standings: [{ entry_id: "e1", points: 6, rank: 1 }],
    });

    const report = await fetchPodReport(apiFetch, "pod-1");

    expect(report).toEqual({
      is_complete: false,
      rounds_played: 2,
      is_partial: true,
      standings: [{ entry_id: "e1", points: 6, rank: 1 }],
    });
    expect(apiFetch).toHaveBeenCalledWith("/pods/pod-1/report", undefined);
  });
});
```

Add to `frontend/src/api/pods.test.ts`, inside the existing
`describe("pods api")` block, after the `"createPod POSTs..."` test:

```ts
  it("completePod POSTs /pods/:id/complete", async () => {
    const apiFetch = fetchReturning({
      id: "p1",
      event_id: "e1",
      format_slug: "swiss",
      game_slug: "generic",
      completed_at: "2026-08-05T12:00:00Z",
    });

    const pod = await completePod(apiFetch, "p1");

    expect(pod.completed_at).toBe("2026-08-05T12:00:00Z");
    expect(apiFetch).toHaveBeenCalledWith("/pods/p1/complete", { method: "POST" });
  });
```

Add `completePod` to the existing import line at the top of
`frontend/src/api/pods.test.ts`:

```ts
import { completePod, createPod, listPodsForEvent } from "./pods";
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/api/report.test.ts src/api/pods.test.ts`
Expected: FAIL — `report.ts` doesn't exist yet (`report.test.ts` fails to
resolve the import); `pods.test.ts` fails because `completePod` isn't
exported yet.

- [ ] **Step 3: Create `frontend/src/api/report.ts`**

```ts
import { apiRequest, type ApiFetch } from "./request";

export interface StandingRow {
  entry_id: string;
  points: number;
  rank: number;
}

export interface PodReport {
  is_complete: boolean;
  rounds_played: number;
  is_partial: boolean;
  standings: StandingRow[];
}

export function fetchPodReport(apiFetch: ApiFetch, podId: string): Promise<PodReport> {
  return apiRequest(apiFetch, `/pods/${podId}/report`);
}
```

- [ ] **Step 4: Add `completePod` to `frontend/src/api/pods.ts`**

Append to the end of the file:

```ts
export function completePod(apiFetch: ApiFetch, podId: string): Promise<PodRead> {
  return apiRequest(apiFetch, `/pods/${podId}/complete`, { method: "POST" });
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/api/report.test.ts src/api/pods.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/report.ts frontend/src/api/report.test.ts frontend/src/api/pods.ts frontend/src/api/pods.test.ts
git commit -m "feat(frontend): add report.ts API module and completePod"
```

---

### Task 4: Report screen

**Files:**
- Create: `frontend/src/routes/Report.tsx`
- Test: `frontend/src/routes/Report.test.tsx`
- Modify: `frontend/src/routes/router.tsx`
- Modify: `frontend/src/routes/EventDetail.tsx`
- Modify: `frontend/src/routes/EventDetail.test.tsx`

**Interfaces:**
- Consumes: `fetchPodReport`, `type PodReport`, `type StandingRow` and
  `completePod` from Task 3; `listEntries`, `type EntryRead` from
  `frontend/src/api/entries.ts` (existing); `useAuth` from
  `frontend/src/auth/AuthContext.tsx` (existing); `ErrorBanner` from
  `frontend/src/components/ErrorBanner.tsx` (existing).
- Produces: `Report` component (default screen for `/pods/:podId/report`)
  — last task in this plan, nothing downstream consumes it.

- [ ] **Step 1: Write the failing component tests**

Create `frontend/src/routes/Report.test.tsx`:

```tsx
import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { Report } from "./Report";

const ENTRIES = [
  { id: "e1", pod_id: "pod-1", player_uuid: "u1", source_system: "opentourney-ui", metadata: { display_name: "Ash" } },
  { id: "e2", pod_id: "pod-1", player_uuid: "u2", source_system: "opentourney-ui", metadata: { display_name: "Misty" } },
];

const COMPLETE_REPORT = {
  is_complete: true,
  rounds_played: 2,
  is_partial: false,
  standings: [
    { entry_id: "e1", points: 6, rank: 1 },
    { entry_id: "e2", points: 3, rank: 2 },
  ],
};

function renderReport(personaLabel?: string) {
  renderWithProviders(<Report />, {
    path: "/pods/pod-1/report",
    routePath: "/pods/:podId/report",
    personaLabel,
  });
}

describe("Report", () => {
  it("shows ranked standings with entry names and points", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json(COMPLETE_REPORT)),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();

    const rows = await screen.findAllByRole("row");
    // rows[0] is the header row.
    expect(rows[1]).toHaveTextContent("1");
    expect(rows[1]).toHaveTextContent("Ash");
    expect(rows[1]).toHaveTextContent("6");
    expect(rows[2]).toHaveTextContent("2");
    expect(rows[2]).toHaveTextContent("Misty");
    expect(rows[2]).toHaveTextContent("3");
  });

  it("shows a partial-round banner when is_partial is true", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json({ ...COMPLETE_REPORT, is_partial: true })),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();

    expect(await screen.findByText(/standings reflect completed rounds only/)).toBeInTheDocument();
  });

  it("shows a not-yet-complete banner when is_complete is false", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json({ ...COMPLETE_REPORT, is_complete: false })),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();

    expect(await screen.findByText(/not yet completed/)).toBeInTheDocument();
  });

  it("shows neither banner once the pod is complete and not partial", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json(COMPLETE_REPORT)),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();
    await screen.findByText("Ash");

    expect(screen.queryByText(/standings reflect completed rounds only/)).not.toBeInTheDocument();
    expect(screen.queryByText(/not yet completed/)).not.toBeInTheDocument();
  });

  it("lets the Organizer complete the pod when the report isn't partial", async () => {
    let completed = false;
    server.use(
      http.get("/pods/pod-1/report", () =>
        HttpResponse.json({ ...COMPLETE_REPORT, is_complete: completed }),
      ),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      http.post("/pods/pod-1/complete", () => {
        completed = true;
        return HttpResponse.json({ id: "pod-1", event_id: "event-1", format_slug: "swiss", game_slug: "generic", completed_at: "2026-08-05T12:00:00Z" });
      }),
    );

    renderReport();
    fireEvent.click(await screen.findByRole("button", { name: "Complete Pod" }));

    expect(await screen.findByRole("button", { name: "Complete Pod" })).toBeDisabled();
  });

  it("disables Complete Pod when the report is partial", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json({ ...COMPLETE_REPORT, is_complete: false, is_partial: true })),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();

    expect(await screen.findByRole("button", { name: "Complete Pod" })).toBeDisabled();
  });

  it("hides Complete Pod for non-Organizer personas", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json({ ...COMPLETE_REPORT, is_complete: false })),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport("Player");

    await screen.findByText("Ash");
    expect(screen.queryByRole("button", { name: "Complete Pod" })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/routes/Report.test.tsx`
Expected: FAIL — `./Report` doesn't exist yet.

- [ ] **Step 3: Create `frontend/src/routes/Report.tsx`**

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { listEntries, type EntryRead } from "../api/entries";
import { completePod } from "../api/pods";
import { fetchPodReport } from "../api/report";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

function displayNameFor(entries: EntryRead[] | undefined, entryId: string): string {
  const entry = entries?.find((candidate) => candidate.id === entryId);
  return entry?.metadata.display_name ?? entryId;
}

export function Report() {
  const { podId } = useParams<{ podId: string }>();
  if (!podId) throw new Error("Report rendered without a podId route param");

  const { apiFetch, currentPersona } = useAuth();
  const queryClient = useQueryClient();
  const isOrganizer = currentPersona.role === "organizer";

  const reportQuery = useQuery({
    queryKey: ["report", podId],
    queryFn: () => fetchPodReport(apiFetch, podId),
  });
  const entriesQuery = useQuery({
    queryKey: ["entries", podId],
    queryFn: () => listEntries(apiFetch, podId),
  });

  const completeMutation = useMutation({
    mutationFn: () => completePod(apiFetch, podId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["report", podId] }),
  });

  const report = reportQuery.data;

  return (
    <div>
      <p className="mb-2">
        <Link to={`/pods/${podId}/pairings`} className="text-sm text-blue-600 underline">
          Back to Pairings
        </Link>
      </p>
      <h2 className="mb-4 text-lg font-semibold">Report</h2>
      <ErrorBanner error={reportQuery.error ?? entriesQuery.error ?? completeMutation.error} />

      {(reportQuery.isLoading || entriesQuery.isLoading) && <p>Loading…</p>}

      {report && (
        <>
          {report.is_partial && (
            <p className="mb-2 rounded border border-yellow-300 bg-yellow-50 px-3 py-2 text-sm text-yellow-800">
              Latest round not fully reported — standings reflect completed rounds only.
            </p>
          )}
          {!report.is_complete && (
            <p className="mb-4 rounded border border-yellow-300 bg-yellow-50 px-3 py-2 text-sm text-yellow-800">
              Pod not yet completed — this is a live view, not final results.
            </p>
          )}

          {isOrganizer && (
            <button
              onClick={() => completeMutation.mutate()}
              disabled={completeMutation.isPending || report.is_partial || report.is_complete}
              title={
                report.is_complete
                  ? "Pod is already complete"
                  : report.is_partial
                    ? "The latest round must be fully reported before completing the pod"
                    : undefined
              }
              className="mb-4 rounded bg-blue-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              Complete Pod
            </button>
          )}

          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left">
                <th className="py-1 pr-4">Rank</th>
                <th className="py-1 pr-4">Entry</th>
                <th className="py-1">Points</th>
              </tr>
            </thead>
            <tbody>
              {report.standings.map((row) => (
                <tr key={row.entry_id} className="border-b border-gray-100">
                  <td className="py-1 pr-4">{row.rank}</td>
                  <td className="py-1 pr-4">{displayNameFor(entriesQuery.data, row.entry_id)}</td>
                  <td className="py-1">{row.points}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Wire the route in `frontend/src/routes/router.tsx`**

Replace the placeholder `{ path: "pods/:podId/report", element: <div>Report</div> }`
entry, and add the import:

```tsx
import { createBrowserRouter } from "react-router";
import { EventDetail } from "./EventDetail";
import { EventList } from "./EventList";
import { Layout } from "./Layout";
import { NewEvent } from "./NewEvent";
import { Pairings } from "./Pairings";
import { Report } from "./Report";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <EventList /> },
      { path: "events/new", element: <NewEvent /> },
      { path: "events/:eventId", element: <EventDetail /> },
      { path: "pods/:podId/pairings", element: <Pairings /> },
      { path: "pods/:podId/report", element: <Report /> },
    ],
  },
]);
```

- [ ] **Step 5: Add a "View Report" link on the Event detail screen**

In `frontend/src/routes/EventDetail.tsx`, next to the existing "View
Pairings" link (around line 53-55), add:

```tsx
            <Link to={`/pods/${pod.id}/pairings`} className="text-blue-600 underline">
              View Pairings
            </Link>
            {" · "}
            <Link to={`/pods/${pod.id}/report`} className="text-blue-600 underline">
              View Report
            </Link>
```

- [ ] **Step 6: Write the failing test for the new link**

Add to `frontend/src/routes/EventDetail.test.tsx`, after the `"links to
the pairings screen once a pod exists"` test:

```tsx
  it("links to the report screen once a pod exists", async () => {
    server.use(
      http.get("/events/event-1", () => HttpResponse.json(EVENT)),
      http.get("/pods", () => HttpResponse.json([POD])),
      http.get("/entries", () => HttpResponse.json([])),
    );

    renderDetail();

    expect(await screen.findByRole("link", { name: "View Report" })).toHaveAttribute(
      "href",
      "/pods/pod-1/report",
    );
  });
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/routes/Report.test.tsx src/routes/EventDetail.test.tsx`
Expected: PASS

Run the full frontend suite:
Run: `cd frontend && npx vitest run`
Expected: PASS

Type-check:
Run: `cd frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/routes/Report.tsx frontend/src/routes/Report.test.tsx frontend/src/routes/router.tsx frontend/src/routes/EventDetail.tsx frontend/src/routes/EventDetail.test.tsx
git commit -m "feat(frontend): add report screen (FR22)"
```

---

### Task 5: Backend integration test for the full flow's final leg

**Files:**
- Create: `backend/tests/integration/test_report_flow_api.py`

**Interfaces:**
- Consumes: existing `api_client`/`make_token` pytest fixtures (see
  `backend/tests/integration/test_matches_api.py` for the fixture
  contract); existing endpoints `POST /events`, `POST /pods`,
  `POST /entries`, `POST /pods/{id}/rounds`,
  `POST /matches/{id}/result`, `POST /pods/{id}/complete`,
  `GET /pods/{id}/report` — all pre-existing, unchanged.
- Produces: nothing — last task in this plan.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/test_report_flow_api.py`:

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


def test_report_screen_flow_partial_then_complete(api_client, make_token):
    """Mirrors the Phase 7 PR4 Report screen's sequence of API calls:
    view a partial report mid-round, finish reporting, complete the pod,
    and confirm the final report reflects completion.
    """
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    for _ in range(2):
        _add_entry(api_client, token, pod_id)

    round1 = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    match_id = round1["matches"][0]["id"]

    partial_report = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token)).json()
    assert partial_report["is_complete"] is False
    assert partial_report["is_partial"] is True
    assert partial_report["rounds_played"] == 1

    complete_attempt = api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))
    assert complete_attempt.status_code == 409

    api_client.post(
        f"/matches/{match_id}/result",
        json={"result": "entry1_win", "method": "manual_entry"},
        headers=_auth_headers(token),
    )

    reported_report = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token)).json()
    assert reported_report["is_partial"] is False
    assert reported_report["is_complete"] is False
    assert [row["rank"] for row in reported_report["standings"]] == [1, 2]

    complete_response = api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))
    assert complete_response.status_code == 200

    final_report = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token)).json()
    assert final_report["is_complete"] is True
    assert final_report["is_partial"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/integration/test_report_flow_api.py -v`
Expected: FAIL if the test database/fixtures aren't set up (see
`backend/tests/README.md` or `conftest.py` for local setup — same
prerequisites as any other integration test in this suite, no new setup
needed). If fixtures are already configured, this test should PASS on
first run since it only exercises existing, already-tested endpoints —
in that case, skip Step 2's "must fail first" expectation and note in
the commit message that this is a coverage addition, not a RED/GREEN
cycle (no backend code changes are involved, unlike Tasks 1-4).

- [ ] **Step 3: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/integration/test_report_flow_api.py -v`
Expected: PASS

Run the full backend test suite to confirm nothing else broke:
Run: `cd backend && python -m pytest`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_report_flow_api.py
git commit -m "test(backend): cover report-screen flow (partial report, complete-pod race, final report)"
```

---

## After all tasks

This plan's tasks cover unit, component, and integration testing per NFR1.
The **acceptance** layer (manual browser walkthrough per persona against
staging, including hard-refresh checks on `/pods/:podId/report` and
`/events/:eventId`) is the mandatory pre-merge gate from
`~/.claude/CLAUDE.md`'s "Manual verification" section — not a plan task,
performed after all tasks above are complete and the branch is deployed to
staging. The local dev-verification recipe (docker Postgres + uvicorn +
Vite + minted dev JWTs + `PodRole` grants) from Phase 7 PR3 applies
unchanged.
