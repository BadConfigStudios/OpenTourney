# Phase 10 — Entry Drop Tracking + Dynamic Swiss Round-Target (Design)

Date: 2026-08-11
Status: Approved (brainstorming), pending plan/execution
Requirement: FR24, `REQUIREMENTS.md` Build Order phase 10, issue #61, MVP2
Related: issue #63 (Phase 12, Pokémon tiebreak strategy — depends on this
phase's `dropped_at_round` for its dropped-entry win% max, per the Play!
Pokémon Tournament Rules Handbook §5.3.3.1)

---

## 1. Scope

MVP1's `SwissFormat` and the operational API have no concept of a player
dropping mid-tournament — `Entry` has no state beyond its identity and
metadata, `generate_round`/`compute_standings` use every entry
unconditionally, and no round-count target is ever computed or shown to
the organizer (round generation is entirely manual/organizer-triggered,
gated only by "the previous round's matches are all reported").

**In scope:**
- `Entry.dropped_at_round: int | None` — a soft-state flag distinct from
  the existing hard `DELETE /entries/{id}` (which remains the pre-
  tournament "fix a roster mistake" path and is unchanged by this phase).
- `POST /entries/{entry_id}/drop` and `POST /entries/{entry_id}/undrop` —
  organizer-only, mirroring the existing entry-mutation RBAC pattern.
- `SwissFormat.generate_round` excludes dropped entries from the pairing
  pool; `compute_standings` and the tiebreak strategy continue to see
  every entry (dropped included) so match history and final placement
  stay correct — a dropped entry keeps the points/record already earned.
- Round-target: `ceil(log2(active_entry_count))`, computed fresh (no
  stored history) and exposed via `GET /pods/{pod_id}/report`
  (`active_entry_count`, `recommended_rounds` fields added to
  `PodReport`).
- Frontend: Drop/Undrop buttons on `EntryRoster`; an advisory
  round-target line + "changed" banner on `Pairings`, computed by
  diffing the freshly-fetched value against what was last rendered
  (component state, not persisted).

**Out of scope (explicitly deferred):**
- Any enforcement/gating tied to the round-target (e.g. disabling
  "Generate Next Round" once reached) — FR24 says "surface the reason,"
  not "enforce." Purely advisory.
- Backend-side history of round-target changes — the frontend diffs
  client-side against its own last-rendered value; no new schema for
  tracking "previous target."
- Anything Pokémon-specific (tiebreak floor/max-win% treatment of
  dropped entries) — that's issue #63 (Phase 12), which consumes this
  phase's `dropped_at_round` but isn't built here.

## 2. Data model

```python
# backend/app/models/entry.py — add one column
dropped_at_round: Mapped[int | None] = mapped_column(nullable=True, default=None)
```

New Alembic migration. `dropped_at_round` semantics: the last round
number the entry was still active for. Set to the pod's current highest
generated round number at drop time, or `0` if dropped before any round
has been generated. `generate_round`'s pairing pool becomes
`[e for e in entries if e.dropped_at_round is None]`; every other
entry-consuming path (`_compute_standings`, `TiebreakStrategy.compute`,
`compute_standings`'s public API) keeps using the full `entries` sequence
unchanged — dropped entries are still ranked, still show up in
`PodReport.standings`, they just stop appearing in new `Pairing`s.

## 3. API

`POST /entries/{entry_id}/drop`
- Auth: same as existing `delete_entry` (`event_organizer_exists` on the
  entry's pod's event).
- 404 if entry not found. 409 if `dropped_at_round is not None` already,
  or if the pod is complete (`pod.completed_at is not None`).
- Sets `dropped_at_round` to `db.query(Round).filter_by(pod_id=...).count()`
  (0 if no rounds yet). Returns `EntryRead`. Dropping does not touch
  `Match` at all — if the entry has an unreported match in the round
  already generated, it's reported through the existing
  `POST /matches/{match_id}/result` endpoint exactly as before (a forfeit
  is just reported as whatever result actually applies); the drop only
  changes what happens on the *next* `generate_round` call.

`POST /entries/{entry_id}/undrop`
- Same auth/lookup. 409 if `dropped_at_round is None` (nothing to undo).
- Clears `dropped_at_round` to `None`. Returns `EntryRead`.

`EntryRead` gains `dropped_at_round: int | None`.

`PodReport` gains:
```python
active_entry_count: int  # entries with dropped_at_round is None
recommended_rounds: int  # ceil(log2(active_entry_count)), computed at request time
```
Computed in `get_pod_report` (`backend/app/routers/pods.py`) alongside
the existing `standings` computation, using the same `all_entries` query
already in scope there.

## 4. Round-target math

```python
import math

def recommended_rounds(active_entry_count: int) -> int:
    if active_entry_count <= 1:
        return 0
    return math.ceil(math.log2(active_entry_count))
```
`active_entry_count <= 1` (0 or 1 active entries) returns `0` — no
meaningful round target when there's nothing left to pair. This mirrors
existing code's lack of special-casing for degenerate entry counts
elsewhere (e.g. `_pair_round_one` already handles an odd/short list
without a dedicated guard) — `recommended_rounds` just needs to not raise
on `log2(0)` or `log2(1)=0` rounding oddly.

## 5. Frontend

`EntryRoster.tsx`: each entry row gets a "Drop" button (organizer-only,
next to the existing edit/delete controls) that calls the new
`POST /entries/{id}/drop` and invalidates the entries query; a dropped
entry's row shows "Undrop" instead, calling the `undrop` endpoint. Both
disabled once `pod.completed_at` is set (mirrors the existing pattern of
disabling mutations post-completion elsewhere in the UI).

`Pairings.tsx`: fetch `GET /pods/{id}/report` alongside the existing
rounds/entries queries (new `useQuery` keyed `["report", podId]`). Render
`"Recommended rounds: {recommended_rounds} (active entries:
{active_entry_count})"` above the "Generate Next Round" button. Track the
last-rendered `recommended_rounds` in a `useRef`/state value; when the
freshly-fetched value differs from it, show a one-line banner ("Round
target changed from {prev} to {next}") for that render, then update the
tracked value. No gating on the button — stays enabled/disabled purely by
the existing `latestRoundHasUnreportedMatch` logic.

## 6. Testing

- **Unit** (`backend/tests/unit`): `recommended_rounds` math (0, 1, 2, 3,
  4, 5, 8, 9 active entries — boundary and non-power-of-2 cases);
  `SwissFormat.generate_round` excludes a dropped entry from pairing
  while `compute_standings` still ranks it.
- **Integration** (`backend/tests/integration`): `POST /drop`/`undrop`
  RBAC (403 for non-organizer), state-transition 409s (double-drop,
  undrop-when-not-dropped, drop-after-pod-complete), `GET
  /pods/{id}/report`'s `active_entry_count`/`recommended_rounds` before
  and after a drop.
- **Frontend**: `EntryRoster` drop/undrop button rendering and mutation
  calls; `Pairings`' banner-diffing logic (renders banner on change,
  doesn't repeat it on the next unchanged fetch).

## 7. Open questions

None outstanding — all five design sections were reviewed and approved
section-by-section with the owner during brainstorming (2026-08-11).
