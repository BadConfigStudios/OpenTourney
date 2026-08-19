# Phase 17 — Pokémon GameModule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Pokémon TCG `GameModule` (slug `pokemon-tcg`) to the existing pluggable game-module system, with `decklist_url` validation restricted to Limitless shared-deck/decks-list links, and wire it up so it's reachable from the app (pod-creation selector) and shows a Bo1-by-default note on the Report screen.

**Architecture:** Follow the existing `backend/app/games/` pattern (`base.py` ABC, `generic.py` reference implementation, `registry.py` lookup) — add a sibling `pokemon.py` module and register it. No router changes needed: `routers/pods.py` and `routers/entries.py` already validate `game_slug` / call `validate_entry_metadata` generically and turn `ValueError` into HTTP 422. Frontend needs two additions: a `getPod` fetch (doesn't exist yet) and a `gameSlug` param threaded through `createPod` (currently hardcoded to `"generic"`).

**Tech Stack:** Python/FastAPI/SQLAlchemy backend, pytest; React/TypeScript frontend with TanStack Query, msw for test mocking, vitest.

## Global Constraints

- Descriptive only — no rules enforcement, no pairing/tiebreak changes (that's FR28/FR29, Phase 18).
- Match points (`WIN_POINTS=3`, `TIE_POINTS=1`, `LOSS_POINTS=0`) are documented on the module but NOT wired into `swiss.py`/`owp_oomw.py` — those already hardcode the same values; do not touch them.
- No `best_of` / match-format schema field — Bo1-by-default is UI copy only.
- `decklist_url` is optional on `Entry.metadata_`. If present it must be exactly one of:
  - `https://my.limitlesstcg.com/shared/<id>`
  - `https://limitlesstcg.com/decks/list/<id>`

  Scheme must be `https`, host exact match (case-insensitive), path prefix exact match, `<id>` any non-empty remaining path segment. Anything else raises `ValueError`.
- No `decklist_url` edit UI — organizers set it via API/import only.

---

### Task 1: PokemonGameModule + registry

**Files:**
- Create: `backend/app/games/pokemon.py`
- Modify: `backend/app/games/registry.py`
- Test: `backend/tests/unit/test_games.py`
- Test: `backend/tests/unit/test_games_registry.py`

**Interfaces:**
- Consumes: `GameModule` ABC from `backend/app/games/base.py` (`slug: str` attribute, `validate_entry_metadata(self, metadata: dict) -> None` abstract method, raises `ValueError` on invalid metadata).
- Produces: `PokemonGameModule` class in `app.games.pokemon`, importable as `from app.games.pokemon import PokemonGameModule`. Class attributes `PokemonGameModule.WIN_POINTS == 3`, `.TIE_POINTS == 1`, `.LOSS_POINTS == 0`. Instance attribute `.slug == "pokemon-tcg"`. Registered in `GAME_MODULES["pokemon-tcg"]` in `app.games.registry`, resolvable via `get_game_module("pokemon-tcg")`.

- [ ] **Step 1: Write the failing unit tests**

Append to `backend/tests/unit/test_games.py`:

```python
from app.games.pokemon import PokemonGameModule


def test_pokemon_game_module_accepts_metadata_without_decklist_url():
    module = PokemonGameModule()

    module.validate_entry_metadata({})
    module.validate_entry_metadata({"display_name": "Ash"})

    assert module.slug == "pokemon-tcg"


def test_pokemon_game_module_accepts_limitless_shared_url():
    module = PokemonGameModule()

    module.validate_entry_metadata(
        {"decklist_url": "https://my.limitlesstcg.com/shared/69f80675a2d4f984ff635738"}
    )


def test_pokemon_game_module_accepts_limitless_decks_list_url():
    module = PokemonGameModule()

    module.validate_entry_metadata({"decklist_url": "https://limitlesstcg.com/decks/list/28236"})


def test_pokemon_game_module_rejects_wrong_host():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata({"decklist_url": "https://evil.example.com/shared/123"})


def test_pokemon_game_module_rejects_wrong_path():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata(
            {"decklist_url": "https://my.limitlesstcg.com/tournament/123"}
        )


def test_pokemon_game_module_rejects_http_scheme():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata(
            {"decklist_url": "http://my.limitlesstcg.com/shared/69f80675a2d4f984ff635738"}
        )


def test_pokemon_game_module_rejects_non_string_decklist_url():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata({"decklist_url": 12345})


def test_pokemon_game_module_rejects_empty_id():
    module = PokemonGameModule()

    with pytest.raises(ValueError, match="decklist_url"):
        module.validate_entry_metadata({"decklist_url": "https://limitlesstcg.com/decks/list/"})


def test_pokemon_match_points_match_handbook_defaults():
    assert PokemonGameModule.WIN_POINTS == 3
    assert PokemonGameModule.TIE_POINTS == 1
    assert PokemonGameModule.LOSS_POINTS == 0
```

`test_games.py` already has `import pytest` at the top — no new import needed for that.

Replace the existing `test_get_game_module_raises_for_unknown_slug` test in
`backend/tests/unit/test_games_registry.py` (it currently asserts
`"pokemon-tcg"` raises — that's no longer true once this task registers it)
with:

```python
import pytest

from app.games.generic import GenericGameModule
from app.games.pokemon import PokemonGameModule
from app.games.registry import get_game_module


def test_get_game_module_returns_generic_module():
    module = get_game_module("generic")

    assert isinstance(module, GenericGameModule)


def test_get_game_module_returns_pokemon_module():
    module = get_game_module("pokemon-tcg")

    assert isinstance(module, PokemonGameModule)


def test_get_game_module_raises_for_unknown_slug():
    with pytest.raises(ValueError, match="unknown game module slug"):
        get_game_module("mtg")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/unit/test_games.py tests/unit/test_games_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.games.pokemon'`

- [ ] **Step 3: Implement `PokemonGameModule`**

Create `backend/app/games/pokemon.py`:

```python
from urllib.parse import urlsplit

from app.games.base import GameModule

_DECKLIST_URL_ERROR = (
    "decklist_url must be an https://my.limitlesstcg.com/shared/<id> or "
    "https://limitlesstcg.com/decks/list/<id> link"
)

_ALLOWED_DECKLIST_HOSTS = {
    "my.limitlesstcg.com": "/shared/",
    "limitlesstcg.com": "/decks/list/",
}


class PokemonGameModule(GameModule):
    """Pokemon TCG game module.

    Descriptive only -- no rules enforcement. Bo1-by-default reporting is
    organizer discretion per the Play! Pokemon Tournament Rules Handbook
    S5.5.6. Match points below match handbook S5.3.2 and are not wired into
    the pairing/scoring engine yet (see Phase 18, FR28/FR29).
    """

    slug = "pokemon-tcg"

    WIN_POINTS = 3
    TIE_POINTS = 1
    LOSS_POINTS = 0

    def validate_entry_metadata(self, metadata: dict) -> None:
        decklist_url = metadata.get("decklist_url")
        if decklist_url is None:
            return
        if not isinstance(decklist_url, str):
            raise ValueError(_DECKLIST_URL_ERROR)

        parts = urlsplit(decklist_url)
        if parts.scheme != "https":
            raise ValueError(_DECKLIST_URL_ERROR)

        path_prefix = _ALLOWED_DECKLIST_HOSTS.get(parts.hostname or "")
        if path_prefix is None or not parts.path.startswith(path_prefix):
            raise ValueError(_DECKLIST_URL_ERROR)

        if not parts.path[len(path_prefix) :]:
            raise ValueError(_DECKLIST_URL_ERROR)
```

`urlsplit(...).hostname` lowercases the host automatically, so the
comparison against the lowercase `_ALLOWED_DECKLIST_HOSTS` keys is already
case-insensitive.

Modify `backend/app/games/registry.py`:

```python
from app.games.base import GameModule
from app.games.generic import GenericGameModule
from app.games.pokemon import PokemonGameModule

GAME_MODULES: dict[str, GameModule] = {
    "generic": GenericGameModule(),
    "pokemon-tcg": PokemonGameModule(),
}


def get_game_module(slug: str) -> GameModule:
    try:
        return GAME_MODULES[slug]
    except KeyError:
        raise ValueError(f"unknown game module slug: {slug!r}") from None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/unit/test_games.py tests/unit/test_games_registry.py -v`
Expected: PASS (all tests, including the modified registry test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/games/pokemon.py backend/app/games/registry.py backend/tests/unit/test_games.py backend/tests/unit/test_games_registry.py
git commit -m "feat(games): add Pokemon TCG game module with decklist_url validation"
```

---

### Task 2: Integration test through the pods/entries API

**Files:**
- Modify: `backend/tests/integration/test_entries_api.py`

**Interfaces:**
- Consumes: `PokemonGameModule` (Task 1) via the registry, transitively through `POST /pods` (`backend/app/routers/pods.py`) and `POST /entries` (`backend/app/routers/entries.py`) — no direct import needed, this test only exercises the HTTP layer.
- Produces: nothing new consumed by later tasks — this task only adds test coverage.

**Why this is a separate task:** Task 1 proves `PokemonGameModule` is correct in isolation (unit test). This task proves it's actually wired through the live API stack (integration test, per this repo's testing-layers convention for boundary-crossing changes) — a pod created with `game_slug="pokemon-tcg"` really does invoke Pokemon's `decklist_url` validation on entry create, not just that the class works standalone.

- [ ] **Step 1: Write the failing integration tests**

In `backend/tests/integration/test_entries_api.py`, change the `_create_pod`
helper to accept an optional `game_slug` (default preserves existing
behavior for every other test in the file):

```python
def _create_pod(api_client, token, game_slug: str = "generic") -> str:
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
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": game_slug},
        headers=_auth_headers(token),
    ).json()["id"]
```

Then append these tests to the same file:

```python
def test_organizer_creates_pokemon_entry_with_valid_decklist_url(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token, game_slug="pokemon-tcg")

    response = api_client.post(
        "/entries",
        json={
            "pod_id": pod_id,
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "metadata": {
                "decklist_url": "https://my.limitlesstcg.com/shared/69f80675a2d4f984ff635738"
            },
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    assert (
        response.json()["metadata"]["decklist_url"]
        == "https://my.limitlesstcg.com/shared/69f80675a2d4f984ff635738"
    )


def test_organizer_creates_pokemon_entry_without_decklist_url(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token, game_slug="pokemon-tcg")

    response = api_client.post(
        "/entries",
        json={
            "pod_id": pod_id,
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "metadata": {},
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 201


def test_pokemon_entry_rejects_non_limitless_decklist_url(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token, game_slug="pokemon-tcg")

    response = api_client.post(
        "/entries",
        json={
            "pod_id": pod_id,
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "metadata": {"decklist_url": "https://example.com/my-deck"},
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/integration/test_entries_api.py -v -k pokemon`
Expected: FAIL if Task 1 wasn't merged first (`game_slug 'pokemon-tcg' is not a recognized game module`); if Task 1 is already done, these should already PASS — in that case skip straight to Step 4's confirmation run and note in the commit that this was verification-only.

- [ ] **Step 3: (No implementation needed)**

Task 1 already made the registry resolve `pokemon-tcg`; the router code in
`entries.py`/`pods.py` already calls `validate_entry_metadata` and turns
`ValueError` into a 422. This task should require no non-test changes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/integration/test_entries_api.py -v`
Expected: PASS (full file, to confirm the `_create_pod` signature change didn't break the other ~10+ existing tests in this file that call it without `game_slug`)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/integration/test_entries_api.py
git commit -m "test(entries): cover Pokemon pod/entry creation through the API"
```

---

### Task 3: Frontend — `getPod`, `createPod(gameSlug)`, pod-creation selector

**Files:**
- Modify: `frontend/src/api/pods.ts`
- Modify: `frontend/src/api/pods.test.ts`
- Modify: `frontend/src/routes/EventDetail.tsx`
- Modify: `frontend/src/routes/EventDetail.test.tsx`

**Interfaces:**
- Consumes: `apiRequest`, `jsonInit`, `ApiFetch` from `frontend/src/api/request.ts` (unchanged).
- Produces: `getPod(apiFetch: ApiFetch, podId: string): Promise<PodRead>` — GETs `/pods/${podId}`. `createPod(apiFetch: ApiFetch, eventId: string, gameSlug: string): Promise<PodRead>` — **signature change**, `gameSlug` is now a required third parameter (was previously hardcoded to `"generic"` internally). Both exported from `frontend/src/api/pods.ts`, consumed by Task 4.

- [ ] **Step 1: Write the failing frontend API tests**

In `frontend/src/api/pods.test.ts`, replace the existing `"createPod POSTs
the fixed swiss/generic slugs"` test and add a new one + a `getPod` test:

```typescript
import { describe, expect, it, vi } from "vitest";
import { completePod, createPod, getPod, listPodsForEvent } from "./pods";

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

  it("getPod GETs /pods/:id", async () => {
    const apiFetch = fetchReturning({
      id: "p1",
      event_id: "e1",
      format_slug: "swiss",
      game_slug: "generic",
      completed_at: null,
    });

    const pod = await getPod(apiFetch, "p1");

    expect(pod.game_slug).toBe("generic");
    expect(apiFetch).toHaveBeenCalledWith("/pods/p1", undefined);
  });

  it("createPod POSTs the given format/game slugs", async () => {
    const apiFetch = fetchReturning(
      { id: "p1", event_id: "e1", format_slug: "swiss", game_slug: "generic", completed_at: null },
      201,
    );

    await createPod(apiFetch, "e1", "generic");

    expect(apiFetch).toHaveBeenCalledWith("/pods", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_id: "e1", format_slug: "swiss", game_slug: "generic" }),
    });
  });

  it("createPod POSTs pokemon-tcg when that game slug is passed", async () => {
    const apiFetch = fetchReturning(
      { id: "p1", event_id: "e1", format_slug: "swiss", game_slug: "pokemon-tcg", completed_at: null },
      201,
    );

    await createPod(apiFetch, "e1", "pokemon-tcg");

    expect(apiFetch).toHaveBeenCalledWith("/pods", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_id: "e1", format_slug: "swiss", game_slug: "pokemon-tcg" }),
    });
  });

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
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/api/pods.test.ts`
Expected: FAIL — `getPod` is not exported; TypeScript compile error fails the whole file.

- [ ] **Step 3: Implement `getPod` and `createPod(gameSlug)`**

Modify `frontend/src/api/pods.ts`:

```typescript
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

export function getPod(apiFetch: ApiFetch, podId: string): Promise<PodRead> {
  return apiRequest(apiFetch, `/pods/${podId}`);
}

export function createPod(apiFetch: ApiFetch, eventId: string, gameSlug: string): Promise<PodRead> {
  return apiRequest(
    apiFetch,
    "/pods",
    jsonInit("POST", { event_id: eventId, format_slug: "swiss", game_slug: gameSlug }),
  );
}

export function completePod(apiFetch: ApiFetch, podId: string): Promise<PodRead> {
  return apiRequest(apiFetch, `/pods/${podId}/complete`, { method: "POST" });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/api/pods.test.ts`
Expected: PASS

- [ ] **Step 5: Write the failing EventDetail test for the selector**

In `frontend/src/routes/EventDetail.test.tsx`, add this test (after the
existing `"creates a pod with the default format/game slugs and then shows
the roster"` test):

```typescript
  it("creates a pod with the selected game slug", async () => {
    let pods: (typeof POD)[] = [];
    const pokemonPod = { ...POD, game_slug: "pokemon-tcg" };
    server.use(
      http.get("/events/event-1", () => HttpResponse.json(EVENT)),
      http.get("/pods", () => HttpResponse.json(pods)),
      http.post("/pods", async ({ request }) => {
        const body = await request.json();
        expect(body).toEqual({ event_id: "event-1", format_slug: "swiss", game_slug: "pokemon-tcg" });
        pods = [pokemonPod];
        return HttpResponse.json(pokemonPod, { status: 201 });
      }),
      http.get("/entries", () => HttpResponse.json([])),
    );

    renderDetail();
    fireEvent.change(await screen.findByLabelText("Game"), { target: { value: "pokemon-tcg" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Pod" }));

    expect(await screen.findByText("No entries yet.")).toBeInTheDocument();
  });
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/routes/EventDetail.test.tsx -t "creates a pod with the selected game slug"`
Expected: FAIL — no element with accessible label "Game" exists yet

- [ ] **Step 7: Add the game selector to `EventDetail.tsx`**

Modify `frontend/src/routes/EventDetail.tsx`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { getEvent } from "../api/events";
import { createPod, listPodsForEvent } from "../api/pods";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";
import { EntryRoster } from "./EntryRoster";

export function EventDetail() {
  const { eventId } = useParams<{ eventId: string }>();
  if (!eventId) throw new Error("EventDetail rendered without an eventId route param");

  const { apiFetch, currentUser } = useAuth();
  const queryClient = useQueryClient();
  const isOrganizer = currentUser.role === "organizer";

  const eventQuery = useQuery({ queryKey: ["events", eventId], queryFn: () => getEvent(apiFetch, eventId) });
  const podsQuery = useQuery({
    queryKey: ["pods", eventId],
    queryFn: () => listPodsForEvent(apiFetch, eventId),
  });

  const [gameSlug, setGameSlug] = useState("generic");

  const createPodMutation = useMutation({
    mutationFn: () => createPod(apiFetch, eventId, gameSlug),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pods", eventId] }),
  });

  const pod = podsQuery.data?.[0];

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold">
        {eventQuery.data ? eventQuery.data.name : "…"}
      </h2>
      {eventQuery.data && <p className="mb-4 text-sm text-gray-600">{eventQuery.data.date}</p>}
      <ErrorBanner error={eventQuery.error ?? podsQuery.error ?? createPodMutation.error} />

      {podsQuery.data && !pod && (
        <div className="mb-6">
          <p className="mb-2 text-sm text-gray-600">This event has no pod yet.</p>
          {isOrganizer && (
            <div className="flex items-center gap-2">
              <select
                aria-label="Game"
                value={gameSlug}
                onChange={(event) => setGameSlug(event.target.value)}
                className="rounded border border-gray-300 px-2 py-1.5 text-sm"
              >
                <option value="generic">Generic</option>
                <option value="pokemon-tcg">Pokémon TCG</option>
              </select>
              <button
                onClick={() => createPodMutation.mutate()}
                disabled={createPodMutation.isPending}
                className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
              >
                Create Pod
              </button>
            </div>
          )}
        </div>
      )}

      {pod && (
        <>
          <p className="mb-4">
            <Link to={`/pods/${pod.id}/pairings`} className="text-blue-600 underline">
              View Pairings
            </Link>
            {" · "}
            <Link to={`/pods/${pod.id}/report`} className="text-blue-600 underline">
              View Report
            </Link>
          </p>
          <EntryRoster podId={pod.id} podCompletedAt={pod.completed_at} />
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/routes/EventDetail.test.tsx`
Expected: PASS (all tests in the file, including the pre-existing "creates a
pod with the default format/game slugs" test — default `<select>` value is
still `"generic"`, so its assertion is unaffected)

- [ ] **Step 9: Commit**

```bash
git add frontend/src/api/pods.ts frontend/src/api/pods.test.ts frontend/src/routes/EventDetail.tsx frontend/src/routes/EventDetail.test.tsx
git commit -m "feat(frontend): add game selector to pod creation and getPod fetch"
```

---

### Task 4: Frontend — Bo1-by-default note on the Report page

**Files:**
- Modify: `frontend/src/routes/Report.tsx`
- Modify: `frontend/src/routes/Report.test.tsx`

**Interfaces:**
- Consumes: `getPod(apiFetch, podId): Promise<PodRead>` from `frontend/src/api/pods.ts` (Task 3). `PodRead.game_slug: string`.
- Produces: nothing consumed by later tasks — this is the last task.

- [ ] **Step 1: Add a shared default `/pods/:id` handler and the failing test**

`Report.test.tsx` has 11 existing `it(...)` blocks, none of which mock
`GET /pods/pod-1` (that endpoint isn't called yet). Rather than editing all
11, add one `beforeEach` right after the `describe("Report", () => {` line
that registers a default handler every test inherits; individual tests can
still override it with their own `server.use(...)` the same way they
already override `/pods/pod-1/report`.

At the top of `frontend/src/routes/Report.test.tsx`, change:

```typescript
import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
```

to:

```typescript
import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
```

Immediately after `describe("Report", () => {`, add:

```typescript
  beforeEach(() => {
    server.use(
      http.get("/pods/pod-1", () =>
        HttpResponse.json({
          id: "pod-1",
          event_id: "event-1",
          format_slug: "swiss",
          game_slug: "generic",
          completed_at: null,
        }),
      ),
    );
  });
```

Then add these two new tests at the end of the `describe` block (before
its closing `});`):

```typescript
  it("shows a Bo1-by-default note for a Pokemon pod", async () => {
    server.use(
      http.get("/pods/pod-1", () =>
        HttpResponse.json({
          id: "pod-1",
          event_id: "event-1",
          format_slug: "swiss",
          game_slug: "pokemon-tcg",
          completed_at: null,
        }),
      ),
      http.get("/pods/pod-1/report", () => HttpResponse.json(COMPLETE_REPORT)),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();

    expect(await screen.findByText(/best-of-1 by default/)).toBeInTheDocument();
  });

  it("hides the Bo1-by-default note for a non-Pokemon pod", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json(COMPLETE_REPORT)),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();
    await screen.findByText("Ash");

    expect(screen.queryByText(/best-of-1 by default/)).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd frontend && npx vitest run src/routes/Report.test.tsx -t "Bo1-by-default"`
Expected: FAIL — no such text rendered yet

- [ ] **Step 3: Add the pod query and note to `Report.tsx`**

Modify `frontend/src/routes/Report.tsx`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { displayNameFor, listEntries } from "../api/entries";
import { completePod, getPod } from "../api/pods";
import { fetchPodReport } from "../api/report";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";

export function Report() {
  const { podId } = useParams<{ podId: string }>();
  if (!podId) throw new Error("Report rendered without a podId route param");

  const { apiFetch, currentUser } = useAuth();
  const queryClient = useQueryClient();
  const isOrganizer = currentUser.role === "organizer";

  const podQuery = useQuery({
    queryKey: ["pods", podId],
    queryFn: () => getPod(apiFetch, podId),
  });
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["report", podId] });
      queryClient.invalidateQueries({ queryKey: ["rounds", podId] });
    },
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
      <ErrorBanner error={reportQuery.error ?? entriesQuery.error ?? podQuery.error ?? completeMutation.error} />

      {podQuery.data?.game_slug === "pokemon-tcg" && (
        <p className="mb-4 rounded border border-gray-300 bg-gray-50 px-3 py-2 text-sm text-gray-700">
          Reported as best-of-1 by default — organizer discretion per Play! Pokémon rules §5.5.6.
        </p>
      )}

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

          {report.standings.length === 0 ? (
            <p>No standings yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left">
                  <th className="py-1 pr-4">Rank</th>
                  <th className="py-1 pr-4">Entry</th>
                  <th className="py-1 pr-4">Points</th>
                  <th className="py-1 pr-4">OMW%</th>
                  <th className="py-1">OOMW%</th>
                </tr>
              </thead>
              <tbody>
                {report.standings.map((row) => (
                  <tr key={row.entry_id} className="border-b border-gray-100">
                    <td className="py-1 pr-4">{row.rank}</td>
                    <td className="py-1 pr-4">{displayNameFor(entriesQuery.data, row.entry_id)}</td>
                    <td className="py-1 pr-4">{row.points}</td>
                    <td className="py-1 pr-4">{(row.tiebreakers[0] * 100).toFixed(1)}%</td>
                    <td className="py-1">{(row.tiebreakers[1] * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/routes/Report.test.tsx`
Expected: PASS (all 13 tests in the file — the 11 pre-existing ones now
implicitly rely on the `beforeEach` default `/pods/pod-1` handler for a
`game_slug: "generic"` pod, which keeps the Bo1 note hidden for them)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/Report.tsx frontend/src/routes/Report.test.tsx
git commit -m "feat(frontend): show Bo1-by-default note on Report for Pokemon pods"
```

---

### Task 5: Run full test suites and update REQUIREMENTS.md tracker

**Files:**
- Modify: `REQUIREMENTS.md` (mark FR27 done, if the file tracks per-phase completion status — check the existing convention around line 59 and the phase table around line 164 before editing)

**Interfaces:**
- Consumes: nothing new — this is a verification + bookkeeping task.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS, zero failures, zero new warnings introduced by this phase's changes

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: PASS, zero failures

- [ ] **Step 3: Check REQUIREMENTS.md's completion convention**

Read `REQUIREMENTS.md` around line 59 (FR27 row) and line 164 (phase 17
row). If other completed phases in that table are marked with a status
indicator (e.g. a checkmark, a "done" column, a strikethrough — inspect
how Phase 16's FR36 row or an earlier completed row is marked), apply the
same marking to FR27's row and the phase-17 row for consistency. If no
such per-row completion convention exists (i.e. the table is just a static
reference and completion is tracked elsewhere, e.g. GitHub issues/
milestones only), skip this step and do not invent a new convention.

- [ ] **Step 4: Commit (only if Step 3 made a change)**

```bash
git add REQUIREMENTS.md
git commit -m "docs: mark FR27/Phase 17 complete in REQUIREMENTS.md"
```

---

## After this plan

Per this repo's PR conventions: one PR for this phase, `/review`, manual
verification (start the app, create a Pokémon pod via the selector, add an
entry with a valid and an invalid `decklist_url`, view the Report page's
Bo1 note), then owner merge. Close GitHub issue #62 in the PR description.
