# Phase 7 PR3 — Pairings/Seating + BO1 Scoring Design

**Date**: 2026-08-05
**Status**: Approved
**Requirements**: FR20, FR21
**Related**: docs/superpowers/specs/2026-08-04-phase-7-operational-ui-design.md
(parent Phase 7 design, item 3 of "Planned PR breakdown"); PR2 (#37, FR19)

## Summary

Build the `/pods/:podId/pairings` screen: current-round pairings with table
seating, round-history selector (past rounds read-only), inline BO1 result
entry gated by persona, and a "Generate Next Round" action. Adds a link
into this screen from `EventDetail`.

## Scope correction found during design

The parent spec assumed pod-scoped Scorekeeper gating could be checked via
`GET /pods/{id}/roles`, cross-referenced against the current persona's
`sub`. That endpoint is `require_pod_organizer`-gated on the backend (403
for a Scorekeeper persona) — confirmed against
`backend/app/routers/pod_roles.py`. UI gating in this PR is done by
persona role only (`organizer`/`scorekeeper` show the controls, `player`
doesn't); the backend's `pod_staff_allowed` check
(`backend/app/routers/matches.py:22-25`) remains the real enforcement —
a Scorekeeper persona not actually assigned to this specific pod still
gets a real 403 from the backend, surfaced via the existing
`<ErrorBanner>` "not permitted for this persona" path. Fine-grained
per-pod self-check (e.g. a `GET /pods/{id}/roles/me` endpoint) is out of
scope for this PR — not needed to close FR20/FR21.

## Backend change (small addition, in-scope for this PR)

`Match` gains a `method` column (`str`, default `"manual_entry"`),
migration + model + schema update:

- `Match.method: str` (`backend/app/models/match.py`), server default
  `"manual_entry"`.
- `MatchResultUpdate.method: Literal["manual_entry"] = "manual_entry"`
  (`backend/app/schemas/match.py`) — request field, defaults to the only
  method that exists today.
- `MatchRead.method: str` — included in the response.
- `reported_by`/`witnessed_by` stay as-is (already capture reporter
  identity as `f"{source_system}:{player_uuid}"`; `witnessed_by` remains
  set equal to `reported_by`, unchanged from current behavior — no
  separate witness step exists).

This is deliberately minimal. A fuller dual-submission/dispute-
reconciliation model (player-vs-player conflicting claims stored in
`confirmed_by`, a `status` field separate from `result`, per-entry
reporter authorization) was proposed during design review but rejected
for this PR: it solves a workflow with no current UI, no player-
submission endpoint, and no FR requiring it. Tracked as a future GitHub
issue instead of building it ahead of need. `method` exists solely so a
future reporting method can be distinguished later without another
migration.

### Example

Request — `POST /matches/{match_id}/result`:
```json
{ "result": "entry1_win", "method": "manual_entry" }
```

Response (200):
```json
{
  "id": "3f9a1c2e-...",
  "round_id": "a1b2c3d4-...",
  "entry1_id": "e0011111-...",
  "entry2_id": "e0022222-...",
  "result": "entry1_win",
  "reported_by": "opentourney-ui:9c4e5f6a-...",
  "witnessed_by": "opentourney-ui:9c4e5f6a-...",
  "table_number": 3,
  "method": "manual_entry"
}
```

## Frontend

**New API modules** (follow existing `apiRequest`/`jsonInit` pattern from
`frontend/src/api/pods.ts`):

- `frontend/src/api/rounds.ts` — `fetchRounds(podId)` (`GET
  /pods/{id}/rounds`, returns `RoundRead[]` with nested `matches`),
  `generateRound(podId)` (`POST /pods/{id}/rounds`).
- `frontend/src/api/matches.ts` — `reportMatchResult(matchId, result,
  method)` (`POST /matches/{id}/result`).

**`frontend/src/routes/Pairings.tsx`** (replaces the placeholder route in
`router.tsx`):

- `useQuery(['rounds', podId], fetchRounds)` — single fetch per screen
  visit (no per-round-number endpoint exists on the backend; the full
  array is always returned). `useQuery(['entries', podId], fetchEntries)`
  — builds an `entry_id → metadata.display_name` map (falls back to
  `entry.id` per the existing `EntryRoster.tsx` convention).
- Local state `selectedRoundNumber`, default = highest round number
  present. Round-history selector: a row of round-number buttons; picking
  one shows that round's matches from the already-fetched array (no
  refetch). Only the highest-numbered round is editable — earlier rounds
  render read-only regardless of persona.
- Match row: `[Entry1 name] vs [Entry2 name]`, `table_number`. When
  `selectedRoundNumber` is the latest round **and** current persona is
  `organizer` or `scorekeeper`: three buttons (`Entry1 wins` / `Tie` /
  `Entry2 wins`) call `reportMatchResult(matchId, result,
  "manual_entry")`. Already-reported matches (`result !== "unreported"`)
  show the result as text instead of buttons. Bye rows (`entry2_id ===
  null`) show `(bye)`, no buttons, on any persona.
- "Generate Next Round" button, visible to `organizer` persona only:
  disabled (with tooltip) when any non-bye match in the latest round has
  `result === "unreported"` — a client-side hint using already-fetched
  data; the backend 409 (`"round N has an unreported match"`) remains the
  actual guard/race protection. On success: invalidate the rounds query
  and set `selectedRoundNumber` to the new round's number.

**`frontend/src/routes/EventDetail.tsx`**: add a "View Pairings" link to
`/pods/:podId/pairings` once a Pod exists (currently the only place a
`podId` is known client-side).

**Error handling**: reuses the existing `<ErrorBanner>` pattern
(`EventDetail.tsx`/`EntryRoster.tsx`) — React Query `error` state surfaced
per screen; 403 shows "not permitted for this persona"; 409/422 show the
backend `detail` verbatim.

## Testing (NFR1 — TDD throughout)

- **Backend**: extend `backend/tests/integration/test_matches_api.py` to
  assert `method == "manual_entry"` in `MatchRead` responses; extend
  `backend/tests/integration/test_round_match_models.py` for the new
  column (default value, persistence). No new endpoints — no new
  integration test files.
- **Frontend unit**: `api/rounds.ts` / `api/matches.ts` request-shape
  tests (Vitest).
- **Frontend component** (msw-mocked, per Phase 7 PR2 precedent): current
  round shows buttons for `organizer`/`scorekeeper`, none for `player`;
  past-round selection is read-only even for `organizer`; bye row shows
  `(bye)` not buttons; already-reported match shows result text not
  buttons; "Generate Next Round" disabled when latest round has
  unreported matches; successful generate auto-selects the new round.
- **Frontend integration** (real FastAPI app, existing `api_client`/
  `make_token` fixture pattern): full create-event → create-pod →
  add-entries → generate-round → report-result(s) → generate-next-round
  flow, asserting round history accumulates correctly.
- **Acceptance** (mandatory manual gate, per-persona on staging):
  Organizer generates round 1, reports a result via buttons, generates
  round 2; Scorekeeper persona reports a result; Player persona sees
  pairings read-only with no entry controls.

## New dependencies

None beyond what PR1/PR2 already introduced (`react-router`,
`tailwindcss`, `msw`).

## Out of scope

- Final report screen (FR22) — PR4, consumes `GET /pods/{id}/report`.
- Dual-submission/dispute-reconciliation reporting model — tracked as a
  future GitHub issue, not built ahead of need.
- Fine-grained per-pod Scorekeeper self-check endpoint — not needed while
  UI gating is persona-role-based and the backend remains the real
  enforcement point.
- Issues #38 (Event needs time/timezone) and #39 (Event/Pod data-model
  discussion) — carried over from PR2, unrelated to this PR.
