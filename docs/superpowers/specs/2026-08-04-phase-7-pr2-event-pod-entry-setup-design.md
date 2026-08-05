# Phase 7 PR2 — Event/Pod/Entry Setup Screens Design

**Date**: 2026-08-04
**Status**: Approved
**Requirements**: FR19
**Related**: docs/superpowers/specs/2026-08-04-phase-7-operational-ui-design.md (parent spec), Phase 7 PR1 (#36, app shell)

## Summary

Fill in the `/`, `/events/new`, `/events/:eventId` route stubs from PR1 with
real screens so an Organizer can create an Event, create its single Pod, and
build the Entry roster. Pairings (`/pods/:podId/pairings`) and report
(`/pods/:podId/report`) routes stay placeholder stubs — out of scope, built
in PR3/PR4.

## Backend this PR builds against

No backend changes. Existing endpoints (Phase 5c/6):
`POST/GET/PATCH/DELETE /events`, `POST/GET/PATCH/DELETE /pods`,
`POST/GET/PATCH/DELETE /entries`. Only one format module (`swiss`) and one
game module (`generic`) exist; `generic.validate_entry_metadata` accepts
any dict.

## Architecture

**Data-fetching**: typed resource helpers `src/api/events.ts`,
`src/api/pods.ts`, `src/api/entries.ts` — thin functions (`listEvents`,
`createEvent`, `createPod`, `listEntries`, `createEntry`, `updateEntry`,
`deleteEntry`, ...) built on `AuthContext`'s existing `apiFetch`. Each
parses JSON and throws on non-2xx, attaching the backend's `detail` string
to the thrown error so `<ErrorBanner>` can surface it verbatim. React
Query hooks (`useQuery`/`useMutation`) in each screen call these directly
— no generic CRUD factory, no extra hook-abstraction layer.

**Shared component**: `<ErrorBanner>` (new, `src/components/`) renders
React Query's `error.message` / backend `detail` for any screen's mutation
or query error.

**RBAC gating in UI**: Organizer-only actions (create/edit/delete on
Event, Pod, Entry) are hidden — not merely disabled — for non-Organizer
personas. Convenience only; backend remains the enforcement point
(NFR2/FR15), matching the parent spec.

## Screens

Replace the placeholder `<div>` elements in `router.tsx` with real
components:

- **`EventList`** (`/`) — table of events (date, link to detail). "New
  Event" button, Organizer-only. All personas can view the list.
- **`NewEvent`** (`/events/new`) — single `date` field, `POST /events`,
  redirect to `/events/:id` on success. Organizer-gated: route redirects
  non-Organizer personas back to `/`.
- **`EventDetail`** (`/events/:eventId`) — fetches the event and its pod
  via `GET /pods?event_id=`.
  - No pod yet: inline "Create Pod" action, Organizer-only. `format_slug`
    and `game_slug` are auto-filled (`"swiss"`, `"generic"`) and not shown
    as form fields — no second module exists yet to choose between.
    Revisit (add visible selects) when a second format or game module
    ships.
  - Pod exists: Entry roster table (`metadata.display_name`, edit/delete
    per row) plus an "Add Entry" form taking only a display-name input.
    On submit, the UI generates `player_uuid` via `crypto.randomUUID()`
    and sets `source_system` to the fixed value `"opentourney-ui"` —
    matches the walk-in/no-external-registration use case this reference
    UI targets; there's no external system minting UUIDs ahead of time.
    Entry edit only changes `metadata.display_name` (`PATCH` sends the
    full `metadata` object). Roster viewable by all personas; mutations
    Organizer-only.

## Data mapping

- Entry create: `{ player_uuid: crypto.randomUUID(), source_system: "opentourney-ui", metadata: { display_name } }`
- Entry edit: `{ metadata: { display_name } }` (full object per `EntryUpdate` schema)
- Pod create: `{ event_id, format_slug: "swiss", game_slug: "generic" }`

## Error handling

Reuses the parent spec's model: React Query `error`/`isError` state
surfaced via `<ErrorBanner>` per screen; 422 shows backend `detail`
verbatim; a blocked Organizer-only action is hidden rather than shown and
erroring, since gating happens before the request is ever made.

## New dependency

- `msw` (Mock Service Worker) — devDependency, mocks HTTP at the network
  layer for component tests rather than stubbing `apiFetch` internals, so
  tests exercise real request/response shapes. Confirmed with owner
  2026-08-04; log in DECISIONS.md alongside this PR.

## Testing (NFR1 — TDD throughout)

- **Unit**: `src/api/events.ts` / `pods.ts` / `entries.ts` helpers
  (request shape, error parsing) — `apiFetch` mocked, no network.
- **Component**: `EventList`, `NewEvent`, `EventDetail` against
  `msw`-mocked responses — loading/error/empty/populated states, and
  RBAC-hidden actions per persona (Organizer vs Scorekeeper vs Player).
- **Integration** (boundary-crossing, required per Testing Layers): one
  real-FastAPI-backend flow test, using the existing `api_client`/
  `make_token` fixture pattern (`backend/tests/integration/`) — create
  event → create pod → add entries, asserting the API state after the
  flow matches what the UI screens would produce.
- **Acceptance**: manual staging walkthrough for all three personas
  (Organizer/Scorekeeper/Player) before merge — mandatory gate per
  CLAUDE.md, not satisfied by automated tests alone.

## Out of scope

- Pairings/seating, result entry, round generation (PR3)
- Final standings/report screen (PR4)
- Real auth/SSO (unchanged from parent spec — persona switcher only)
- A second format or game module (would add visible Pod-creation selects)
