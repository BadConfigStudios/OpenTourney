# Phase 6 — Match & Tournament Reporting Design

**Closes:** GitHub issue #6 (FR17–FR18, per `REQUIREMENTS.md`).

## Problem

Phase 4 built `SwissFormat.generate_round` (pure Python, no DB, no endpoints —
deferred to Phase 5 per its plan doc). Phase 5 built the operational API
(events/pods/entries/roles CRUD + RBAC + OIDC) but never wired
`generate_round` into a router. As a result, nothing in the running system
can create a `Round` or `Match` row today. Issue #6's acceptance criteria
(match result reporting, witness enforcement, completion detection, final
report) all assume rounds/matches already exist — so this phase must also
add round-generation orchestration, not just result reporting. This was
confirmed with the project owner as in-scope for Phase 6 rather than a
separate blocking issue.

## Non-goals (this phase)

- **Dynamic round-target recalculation from drops.** The owner wants Swiss
  round counts (`ceil(log2(active_entries))`) to react to mid-tournament
  drops (e.g. 5 drops in round 4 of a 20-person pod could end the event
  after round 4 instead of pairing round 5), with the reason surfaced to
  the organizer, plus the ability to drop an entry at all — none of which
  exists in the schema today (`Entry` has no dropped/active concept). This
  is real, owner-confirmed future scope, deliberately deferred to keep
  Phase 6 sized to a single PR. Tracked as FR24 in `REQUIREMENTS.md` and
  GitHub issue (see Follow-ups).
- **Real tiebreaking (OMW%/OOMW%).** Standings ties are broken by UUID
  string, identical to the existing pairing tiebreak in
  `SwissFormat._rank_entries`. Owner-accepted for now: "already randomly
  generated, so it's as good as anything as a tiebreaker." Same precedent
  as issue #12 (pairing has a known rematch-avoidance gap, filed as tech
  debt rather than fixed inline). Real tiebreakers (opponent match win %
  and opponents' opponents' match win %) are scheduled as their own phase
  before release — FR25, Phase 8, issue #27 — not dropped, just sequenced
  after this phase.
- **`confirmed_by`.** The `Match.confirmed_by` JSONB column exists but stays
  unused — no confirm-workflow endpoint this phase. Issue #6's AC doesn't
  call for one. Its presence in the schema already anticipates the
  eventual mobile self-report + organizer-sign-off flow the owner
  described (see FR24 follow-up), so no migration is needed to support it
  later.

## Architecture

### `app/formats/registry.py` (new)

Mirrors the existing `app/games/registry.py` pattern:

```python
FORMATS: dict[str, TournamentFormat] = {"swiss": SwissFormat()}

def get_tournament_format(slug: str) -> TournamentFormat:
    try:
        return FORMATS[slug]
    except KeyError:
        raise ValueError(f"unknown tournament format slug: {slug!r}") from None
```

Closes a small pre-existing gap while here: `POST /pods` validates
`game_slug` but not `format_slug` (`app/routers/pods.py`). Add the same
`try/except ValueError -> 422` guard for `format_slug` using this registry,
matching `_validate_game_slug`'s existing shape.

### `SwissFormat.compute_standings` (rename/publicize)

`app/formats/swiss.py`'s `_compute_standings` and `_rank_entries` are
private module functions today (added Phase 4 for internal pairing use
only). The report endpoint needs the same points computation + ranking.
Expose a public method on `TournamentFormat`:

```python
class TournamentFormat(ABC):
    ...
    @abstractmethod
    def compute_standings(
        self, entries: Sequence[Entry], rounds: Sequence[Round]
    ) -> list[StandingRow]:
        """Return ranked standings for all entries given completed rounds."""
```

`StandingRow` (new dataclass in `app/formats/base.py`, alongside `Pairing`):
`entry_id: uuid.UUID`, `points: int`, `rank: int`. `SwissFormat.compute_standings`
wraps the existing `_compute_standings` + `_rank_entries` logic (same UUID
tiebreak) and assigns `rank` by ranked position (ties share the sort order,
no tied-rank collapsing — e.g. two entries both at 2nd don't both show "2",
they show 2 and 3, since the UUID tiebreak already gives a strict order).
Raises the same `ValueError` on any unreported non-bye match, which callers
(the report endpoint) catch to decide "live/partial" vs "final" reporting —
see the report endpoint below.

### `require_pod_staff` (new RBAC dependency)

`app/auth/dependencies.py` has `require_pod_organizer` (Organizer only) and
`require_pod_access` (Organizer OR any pod role, including plain `User`).
Neither fits "Organizer or Scorekeeper, not plain User" — needed for match
result reporting and stays consistent for any future staff-only action.

```python
def require_pod_staff(
    pod_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Identity:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    is_organizer = event_organizer_exists(db, identity, pod.event_id)
    is_scorekeeper = (
        db.query(PodRole)
        .filter_by(pod_id=pod_id, player_uuid=identity.player_uuid,
                    source_system=identity.source_system, role=PodRoleName.SCOREKEEPER)
        .first()
        is not None
    )
    if not (is_organizer or is_scorekeeper):
        raise HTTPException(status_code=403, detail="Organizer or Scorekeeper role required")
    return identity
```

### `Pod.completed_at` (new column, migration `0007`)

`Mapped[datetime | None]`, nullable, no default. Marks a pod as finished.
Follows the existing hand-written revision convention
(`backend/alembic/versions/000N_*.py`).

## Endpoints (new `app/routers/rounds.py` + `app/routers/matches.py` + additions to `pods.py`)

| Method | Path | RBAC | Behavior |
|---|---|---|---|
| POST | `/pods/{pod_id}/rounds` | `require_pod_organizer` | Loads pod's entries + prior rounds (ordered), calls `get_tournament_format(pod.format_slug).generate_round(...)`, persists `Round` (next `number`) + `Match` rows. Catches the format's `ValueError` (unreported prior match) → 409. If pod has zero entries → 409 ("pod has no entries"). Returns the created round + matches. |
| GET | `/pods/{pod_id}/rounds` | `require_pod_access` | Lists rounds (ordered by `number`) with nested matches. For visibility/testing and the Phase 7 UI later. |
| POST | `/matches/{match_id}/result` | `require_pod_staff` (resolved via `match.round.pod_id`) | Body: `{result: MatchResult}`, must be `ENTRY1_WIN`/`ENTRY2_WIN`/`TIE` (reject `UNREPORTED` as invalid input, 422). 409 if `match.entry2_id is None` (bye — already auto-scored, nothing to report). Sets `result`, and `reported_by = witnessed_by = f"{identity.source_system}:{identity.player_uuid}"` — both fields always equal the caller's identity, since `require_pod_staff` already guarantees Organizer-or-Scorekeeper. Overwrites allowed (correcting a mis-entered result), no extra guard. |
| POST | `/pods/{pod_id}/complete` | `require_pod_organizer` | 409 if `pod.completed_at` already set. 409 if any existing round has an unreported non-bye match (reuses the format's standings computation to detect this, same as round-generation's check). Otherwise sets `completed_at = now()`. Callable after any round, regardless of whether some future target is "reached" — this phase has no target concept, so completion is always the organizer's explicit call. |
| GET | `/pods/{pod_id}/report` | `require_pod_access` | Always available (live leaderboard mid-tournament, final report after `/complete`). Calls `compute_standings`; if it raises (unreported matches exist), returns the partial standings computed from only the fully-reported rounds up to that point, with `is_partial: true` — a live leaderboard shouldn't 409 just because the current round is still in progress. Response: `{is_complete: bool, rounds_played: int, is_partial: bool, standings: [{entry_id, points, rank}]}`. |

## Data flow

1. Organizer creates pod, entries (Phase 5, unchanged).
2. Organizer `POST /pods/{pod_id}/rounds` → round 1 paired (no prior
   results needed) → `Round` + `Match` rows created, `table_number` set
   per existing `SwissFormat` logic.
3. Organizer/Scorekeeper `POST /matches/{match_id}/result` per match.
4. Organizer repeats step 2 for round 2+; blocked by 409 until all of the
   current round's matches are reported.
5. Anytime: `GET /pods/{pod_id}/report` for a live leaderboard.
6. Organizer decides the event is done (all rounds run, or an early stop)
   → `POST /pods/{pod_id}/complete`.
7. `GET /pods/{pod_id}/report` now returns `is_complete: true` — the final
   placement report.

## Testing

TDD (RED → GREEN → REFACTOR) per every task, per `~/.claude/CLAUDE.md`.

- **Integration** (real Postgres, existing `testcontainers` fixtures):
  round-generation 409 on unreported prior round; round-generation 409 on
  empty pod; result-reporting RBAC (Organizer/Scorekeeper allowed, plain
  User rejected); result-reporting 409 on bye match; result-reporting 422
  on `UNREPORTED`; `/complete` 409 paths (already complete, unreported
  matches); `/report` live/partial vs final shape.
- **Unit**: `SwissFormat.compute_standings` ranking (extracted from the
  existing `_compute_standings`/`_rank_entries` unit tests, same fixtures);
  `get_tournament_format` unknown-slug `ValueError`.

## Follow-ups (documented, not built this phase)

- **New FR24** (add to `REQUIREMENTS.md`'s FR table, Phase "TBD — future"):
  dynamic Swiss round-target recalculation (`ceil(log2(active_entries))`,
  recomputed from non-dropped entries before each round's pairing, with
  the reason surfaced to the organizer when the target changes) +
  `Entry.dropped_at_round` + a drop endpoint. Manual early-completion
  (`POST /pods/{pod_id}/complete`, already built this phase) already
  covers "organizer ends the tournament after a desired round" — the
  deferred part is only the *automatic* target recalculation from drops.
- File a new GitHub issue capturing the above, milestone TBD (not MVP1
  unless the owner decides otherwise).
