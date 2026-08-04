# Phase 7 — Operational UI Design

**Date**: 2026-08-04
**Status**: Approved
**Requirements**: FR19, FR20, FR21, FR22, FR26 (BR1); NFR2, NFR4 (auth boundary)
**Related**: DECISIONS.md 2026-08-03 (pre-minted persona tokens + UI persona switcher)

## Summary

Build the reference operational UI an Organizer uses to run an in-person
Swiss event end-to-end: event/pod/entry setup, round pairings with seating,
BO1 result entry gated by RBAC, and a final standings/placement report —
authenticated via a persona switcher that swaps which pre-minted Bearer
token the API client attaches (no real login flow, per DECISIONS.md
2026-08-03).

## Backend API this phase builds against

Phase 6 PR4 (#34, merged 2026-08-04) already shipped the completion/report
API this phase needs — no backend work required before starting the
frontend:

- `POST /pods/{id}/complete` (Organizer-gated): sets `Pod.completed_at`,
  409s if already complete or if the latest round has an unreported match.
- `GET /pods/{id}/report` (pod-access-gated): returns
  `PodReport { is_complete, rounds_played, is_partial, standings: [StandingRowRead { entry_id, points, rank }] }`.
  `is_partial: true` means the latest round isn't fully reported yet, so
  standings reflect only completed rounds — the UI should surface that
  distinction rather than presenting a partial report as final.

(An earlier draft of this spec, written before rebasing onto a stale local
`main`, incorrectly described this as a missing endpoint to be added in
Phase 7. Corrected here — no PR1 backend work needed.)

## Architecture

**App shell**: `main.tsx` → `QueryClientProvider` (existing
`@tanstack/react-query`; amendment, post-review: implemented inside `App.tsx`
rather than `main.tsx`, so `App.test.tsx` can render `<App/>` in isolation
with no external provider ancestor) → `ConfigProvider` (loads runtime `config.json`,
blocks render until loaded) → `AuthProvider` (persona switcher state) →
`BrowserRouter` (new dependency: `react-router`) → routed screens, all
under a shared layout with the persona switcher in a top nav.

**Token delivery (runtime, not build-time)**: pre-minted persona tokens
must not be committed to git or baked into the public JS bundle
(DECISIONS.md 2026-08-03). The frontend container's nginx entrypoint runs
`envsubst` against Helm-secret-injected env vars to generate a
`config.json` (or `window.__CONFIG__` script) at container start, served
alongside the static bundle. `ConfigProvider` fetches it on load. Same
built image works unmodified across environments/customer namespaces —
only the Helm values/secret differ per deploy.

**Persona/auth flow**: `config.json` shape:
`{ personas: [{ label, role, token }] }` for Organizer/Scorekeeper/Player.
`AuthProvider` holds `currentPersona` in React state (default: first
persona, or last choice from `localStorage`), exposed via context. A thin
`apiClient` wraps `fetch`, attaching `Authorization: Bearer <token>` on
every call. Switching persona clears the React Query cache
(`queryClient.clear()`) so no cross-persona data leaks across the switch.

**RBAC gating in UI** (convenience only — backend remains the actual
enforcement point per NFR2/FR15, this doesn't change any trust boundary):

- Organizer-wide actions: gated by which persona is selected (Organizer
  persona = organizer everywhere).
- Pod-scoped Scorekeeper actions (match result entry): gated via existing
  `GET /pods/{id}/roles`, cross-referenced against the current persona's
  `sub`.

**Portability**: this design doesn't affect isolated-namespace-per-customer
deployability — the Helm chart already deploys per namespace (Phase 2);
runtime `config.json` is *more* portable than baked tokens (no rebuild per
customer). The persona-switcher auth model itself stays what
DECISIONS.md 2026-08-03 already scoped: private/single-tenant/throwaway-
cluster only, not real multi-user customer auth. Swapping in real SSO
later is a config-only change (`OIDC_ISSUER`/`OIDC_JWKS_URL`), except the
already-flagged `identity_from_claims` UUID-`sub` assumption breaking on
Google's opaque numeric `sub`.

## Screens & routes

Event/Pod/Entry setup collapses into one flow since v1 constrains the UI
to exactly one Pod per Event (FR8) — no separate pod-list screen.

| Route | Purpose | Gating |
|---|---|---|
| `/` | Event list, "New Event" | Organizer for mutations |
| `/events/new` | Create Event form | Organizer |
| `/events/:eventId` | Event detail: auto-shows its one Pod (create-Pod form if none), Entry roster CRUD | Organizer for mutations, all personas can view |
| `/pods/:podId/pairings` | Current round: pairings + seating (`table_number`), inline BO1 result entry, "Generate Next Round", round-history selector (past rounds read-only) | Organizer generates rounds; Organizer/Scorekeeper (per pod-role check) enter results |
| `/pods/:podId/report` | Standings/placement via `GET /pods/{id}/report` (`is_complete`, `rounds_played`, `is_partial`, ranked `standings`) — reachable any time, banner shown when `is_partial` (latest round not fully reported) or `!is_complete` (Organizer hasn't hit "Complete Pod" yet) so a mid-tournament view is never mistaken for final | Viewable by all personas; "Complete Pod" action Organizer-only |

## Error handling

- API errors (401/403/404/422/500) surface via React Query's `error`
  state through a shared `<ErrorBanner>` per screen; 422 shows the
  backend's `detail` verbatim.
- A gated action blocked for the current persona shows an inline "not
  permitted for this persona" message rather than a generic error —
  should rarely round-trip to the backend given UI-side gating, but the
  backend response still has to be handled since it's the real
  enforcement point.
- `config.json` load failure blocks the whole app with a fatal-error
  screen (no persona tokens means nothing else can function).
- Loading/error states otherwise use React Query's built-in
  `isLoading`/`isError` — no custom loading-state plumbing.

## Testing (NFR1 — TDD throughout)

- **Unit**: `apiClient` token-attach logic, persona-switch cache-clear,
  pod-role gating helper. Vitest + Testing Library (existing setup).
- **Component**: each screen tested against mocked API responses via
  `msw` (new dependency) at the network layer, rather than mocking
  `apiClient` internals — tests exercise real request/response shapes.
- **Integration** (boundary-crossing, required per Testing Layers): at
  least one real frontend-flow test per screen against the actual FastAPI
  app, using the existing `api_client`/`make_token` fixture pattern from
  `backend/tests/integration/test_matches_api.py` — e.g. full
  create-event → create-pod → add-entries flow, and
  generate-round → report-result → generate-next-round → complete-pod →
  view-report flow.
- **Acceptance**: mandatory manual verification gate — browser walkthrough
  per persona (Organizer/Scorekeeper/Player) against staging before each
  PR merges.

## New dependencies (flagged for owner sign-off, log in DECISIONS.md)

- `react-router` — routing
- `tailwindcss` — styling
- `msw` — API mocking for component tests

## Future work tracked, not in this phase's scope

- **NFR6** (new, added to REQUIREMENTS.md this session): publish OpenAPI
  contract metadata beyond schema shape — realistic constraints and
  fake/mock example payloads per endpoint, so third-party API consumers
  (BR2) can integrate/test without a live instance. Post-MVP1, not
  required to close this phase.

## Planned PR breakdown (for writing-plans)

No backend PR needed — `POST /pods/{id}/complete` and
`GET /pods/{id}/report` already exist (Phase 6 PR4, #34).

1. Frontend app shell: config loader, persona switcher, `apiClient`,
   router skeleton, Tailwind setup.
2. Event/Pod/Entry setup screens (FR19).
3. Pairings/seating + scoring screens (FR20, FR21).
4. Final report screen (FR22, consumes `GET /pods/{id}/report`).
