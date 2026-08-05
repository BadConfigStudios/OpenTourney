# Phase 7 PR4 — Final Report Screen Design

**Date**: 2026-08-05
**Status**: Approved
**Requirements**: FR22 (BR1)
**Related**: `docs/superpowers/specs/2026-08-04-phase-7-operational-ui-design.md` (parent
Phase 7 spec, item 4 of 4 in its PR breakdown), `docs/superpowers/specs/2026-08-05-phase-7-pr3-pairings-scoring-design.md`
(PR3, source of the route-collision pattern this PR replaces)

## Summary

Build the standings/placement report screen (`/pods/:podId/report`) that
consumes the already-existing `GET /pods/{id}/report` (Phase 6 PR4, #34) and
`POST /pods/{id}/complete`. This is the final screen of Phase 7's
end-to-end operational UI flow: create event/pod/entries → generate rounds
→ report results → complete pod → view final standings.

No backend work required — both endpoints already exist and are unchanged
by this PR.

## Route collision: Accept-header dispatch

PR4's route, `/pods/:podId/report`, collides with a **real** backend
endpoint at the identical path (`GET /pods/{id}/report`), unlike PR3's
`/pods/:podId/pairings`, which had no backend counterpart and got a
contained nginx regex / Vite `bypass()` carve-out. A literal-path
collision can't be resolved by path matching alone — nginx/Vite can't
tell "browser hard-refreshing the SPA" from "a client calling the real
API" by URL, since both are plain `GET` requests to the same path.

**Decision**: dispatch on the `Accept` request header instead of the
path. Browser navigation (address-bar load, hard refresh, clicking a
bookmarked/shared link) sends `Accept: text/html,application/xhtml+xml,...`
by default; the frontend's own API calls will explicitly send
`Accept: application/json`. This distinguishes the two cases regardless
of path overlap, and generalizes to *any* current or future path
collision — not just this one.

**Scope**: applied to all four backend-proxied prefixes (`/events`,
`/pods`, `/entries`, `/matches`), replacing PR3's regex/`bypass()`
carve-out for `/pairings` (no longer needed — the generic mechanism
covers it) and retiring the still-open `/events/:eventId` collision
noted in DEVELOPMENT.md as a known limitation.

### Implementation

- **`frontend/nginx.conf`**: an nginx `map $http_accept $accepts_html { ... }`
  block (regex match on `text/html`) feeds a variable checked inside each of
  the four prefix `location` blocks: `if ($accepts_html) { return 418; }`,
  falling through to `proxy_pass http://backend:8000` otherwise. (`try_files`
  isn't valid inside an `if` block, and `location` blocks can't branch on
  headers directly, hence the `map` + `return`.) A server-level
  `error_page 418 = /index.html;` directive performs an internal redirect
  to the SPA shell, handled by `location /`'s existing `try_files`; a
  server-level `add_header Vary Accept always;` ensures HTTP caches don't
  conflate the SPA and API responses for the same URL. The `/pairings`
  regex `location` is removed.
- **`frontend/vite.config.ts`**: each prefix's proxy `bypass()` inspects
  `req.headers.accept`; if it contains `text/html`, return the request's
  own URL (falls through to Vite's SPA handling) — otherwise let the
  proxy through. The `/pods` bypass's existing `/pairings`-specific regex
  check is removed in favor of this generic check.
- **`frontend/src/auth/AuthContext.tsx`**: `apiFetch` (the single choke
  point every API call already flows through, since it attaches the
  `Authorization` header) also sets `Accept: application/json` in its
  headers merge — today no `Accept` header is sent (fetch defaults to
  `*/*`, which the `map`'s `text/html` regex correctly does not match,
  but making it explicit removes ambiguity and documents the contract
  other API consumers should follow). One-line change, one call site,
  applies to every request uniformly — no per-module edits to
  `request.ts` or its callers needed.
- **`DEVELOPMENT.md`**: replace the "Known limitation" paragraph
  (`/events/:eventId` and `/pods/:podId/report` colliding) with a short
  description of the Accept-header dispatch mechanism, including its one
  real edge case: a non-browser HTTP client hitting either SPA route
  without an explicit `Accept: text/html` (e.g. plain `curl`) is routed to
  the backend, not the SPA — correct behavior for an API consumer, worth
  naming given BR2's third-party-consumer concern.

## Report screen (`/pods/:podId/report`)

- **Data**: `GET /pods/{id}/report` (`PodReport`) via React Query, plus
  `listEntries(apiFetch, podId)` (existing, already used by Pairings) to
  map `entry_id` → display name.
- **Banners** (reusing the existing non-error informational banner
  pattern): shown when `is_partial` ("Latest round not fully reported —
  standings reflect completed rounds only") and/or `!is_complete` ("Pod
  not yet completed — this is a live view, not final results"). Both can
  render simultaneously; they're independent conditions.
- **Standings table**: columns Rank, Entry, Points, rows in the order
  `PodReport.standings` already returns (backend pre-sorts by rank).
- **Complete Pod button**: visible only when `currentPersona.role ===
  "organizer"`. Calls a new `completePod(apiFetch, podId)` (`POST
  /pods/{id}/complete`) added to `frontend/src/api/pods.ts`. Disabled
  (with an explanatory `title` tooltip, mirroring Pairings' "Generate Next
  Round" disable pattern) when `is_partial` or `is_complete` is already
  true. On success, invalidate the `["report", podId]` query.
- **Nav**: "Back to Pairings" link, mirroring Pairings' existing "Back to
  Events" link.
- **Loading/error**: React Query `isLoading`/`error` through
  `<ErrorBanner>`, consistent with Pairings and EventDetail.

## Error handling

Standard pattern from the parent Phase 7 spec: API errors surface via
`<ErrorBanner>`; a 409 from `POST /pods/{id}/complete` (already-complete
or unreported-match races) surfaces the backend's `detail` verbatim,
since the UI's disable logic is convenience-only and the backend remains
the real enforcement point.

## Testing (NFR1)

- **Unit**: no new business logic beyond the `Accept` header addition to
  `AuthContext.tsx`'s `apiFetch` — existing `AuthContext.test.tsx` updated
  to assert the header is sent alongside `Authorization`.
- **Component** (`msw`): report screen against mocked `GET
  /pods/{id}/report` + entries — cases: complete, partial, in-progress
  (neither complete nor partial), empty-pod (no rounds played). Complete
  Pod button visibility/disable across persona × state combinations.
  Error state.
- **Integration**: extends the parent spec's planned end-to-end flow
  (`generate-round → report-result → generate-next-round → complete-pod →
  view-report`) against the real FastAPI app — this PR completes that
  flow's final leg.
- **Route-dispatch verification**: no existing automated harness covers
  `nginx.conf`/`vite.config.ts` directly; verified manually (`curl` with
  and without `Accept: text/html` against staging) as part of the manual
  verification gate — consistent with how PR3's carve-out was verified.
  Documented here as a coverage gap, not fixed in this PR.
- **Acceptance**: manual browser walkthrough per persona (Organizer,
  Scorekeeper, Player) against staging before merge, including a hard
  refresh on `/pods/:podId/report` and `/events/:eventId` to confirm the
  Accept-header dispatch actually resolves both collisions.

## Out of scope

- Any change to `PodReport`'s shape or the backend's standings
  computation — both are Phase 6, unchanged here.
- Re-opening PR3's dispute/correction-of-a-misreported-result gap (issue
  #53) or the missing-`PodRole`-grant-UI gap (issue #54) — both remain
  deferred, unaffected by this PR.
