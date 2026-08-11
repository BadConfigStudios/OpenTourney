# Phase 10 — Entry Drop Tracking + Dynamic Swiss Round-Target Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an organizer drop/undrop an entry mid-tournament (preserving match history, excluding them from future pairings) and surface a dynamically-recomputed recommended round count on the report/pairings screens.

**Architecture:** One new nullable column (`Entry.dropped_at_round`) drives everything — `SwissFormat.generate_round` filters its pairing pool on it while standings/tiebreak math keeps seeing every entry; two new organizer-only endpoints (`POST /entries/{id}/drop`, `/undrop`) set/clear it; a small pure-function module computes `ceil(log2(active_entries))`; `PodReport` gains two fields exposing the live count and recommendation; the frontend adds Drop/Undrop buttons and an advisory banner, no gating.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic (backend), React + TypeScript + TanStack Query + MSW (frontend), pytest (backend tests), Vitest + Testing Library (frontend tests).

## Global Constraints

- FR24 (`REQUIREMENTS.md`): recompute `ceil(log2(active_entries))` from non-dropped entries before each round's pairing, surface the reason to the organizer when it changes; entry drop tracking (`Entry.dropped_at_round`).
- Round-target is advisory only — no gating on round generation or pod completion.
- Dropping an entry never touches `Match` rows — an already-generated round's match is reported normally through the existing `POST /matches/{match_id}/result` endpoint.
- `compute_standings` and `TiebreakStrategy.compute` always receive the full, unfiltered entry list — only the pairing pool (`generate_round`) filters on `dropped_at_round`.
- `dropped_at_round` semantics: the pod's round count *at the time of the drop* (0 if dropped before any round exists) — not a "which round they lost in" value.

---

## File Structure

- `backend/app/models/entry.py` — modify, add `dropped_at_round` column.
- `backend/alembic/versions/0010_add_entry_dropped_at_round.py` — new migration.
- `backend/app/schemas/entry.py` — modify, `EntryRead` gains `dropped_at_round`.
- `backend/app/formats/swiss.py` — modify, `generate_round` filters its pairing pool.
- `backend/app/formats/round_target.py` — new, `recommended_rounds(active_entry_count: int) -> int`.
- `backend/app/routers/entries.py` — modify, add `drop_entry`/`undrop_entry` endpoints.
- `backend/app/schemas/report.py` — modify, `PodReport` gains `active_entry_count`/`recommended_rounds`.
- `backend/app/routers/pods.py` — modify, `get_pod_report` computes and returns the two new fields.
- `frontend/src/api/entries.ts` — modify, `EntryRead` gains `dropped_at_round`; add `dropEntry`/`undropEntry`.
- `frontend/src/api/report.ts` — modify, `PodReport` gains `active_entry_count`/`recommended_rounds`.
- `frontend/src/routes/EntryRoster.tsx` — modify, Drop/Undrop buttons.
- `frontend/src/routes/EventDetail.tsx` — modify, pass `podCompletedAt` prop to `EntryRoster`.
- `frontend/src/routes/Pairings.tsx` — modify, fetch `PodReport`, render advisory banner.

---

## Task 1: Data model — `Entry.dropped_at_round`

**Files:**
- Modify: `backend/app/models/entry.py`
- Create: `backend/alembic/versions/0010_add_entry_dropped_at_round.py`
- Modify: `backend/app/schemas/entry.py`
- Test: `backend/tests/integration/test_entry_model.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Entry.dropped_at_round: int | None` (SQLAlchemy `Mapped[int | None]`), consumed by Tasks 2, 4, 5.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/integration/test_entry_model.py`:

```python
def test_entry_dropped_at_round_defaults_to_none(db_session):
    pod = _make_pod(db_session)
    entry = Entry(
        pod_id=pod.id,
        player_uuid=uuid.uuid4(),
        source_system="club-checkin",
        metadata_={},
    )
    db_session.add(entry)
    db_session.commit()

    assert entry.dropped_at_round is None


def test_entry_dropped_at_round_persists(db_session):
    pod = _make_pod(db_session)
    entry = Entry(
        pod_id=pod.id,
        player_uuid=uuid.uuid4(),
        source_system="club-checkin",
        metadata_={},
        dropped_at_round=2,
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    assert entry.dropped_at_round == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/integration/test_entry_model.py -v`
Expected: FAIL with `TypeError: 'dropped_at_round' is an invalid keyword argument for Entry` (or an `AttributeError` on the plain-default test).

- [ ] **Step 3: Add the column to the model**

In `backend/app/models/entry.py`, add the import and column (`Entry`'s docstring and existing fields stay as-is):

```python
from sqlalchemy import ForeignKey, UniqueConstraint
```
(already imported) — add below the existing `metadata_` column definition:

```python
    dropped_at_round: Mapped[int | None] = mapped_column(nullable=True, default=None)
```

- [ ] **Step 4: Write the migration**

Create `backend/alembic/versions/0010_add_entry_dropped_at_round.py`:

```python
"""add dropped_at_round to entries

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-11

"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("entries", sa.Column("dropped_at_round", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("entries", "dropped_at_round")
```

- [ ] **Step 5: Add the field to `EntryRead`**

In `backend/app/schemas/entry.py`, add to `EntryRead` (after the existing `metadata` field):

```python
    dropped_at_round: int | None
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/integration/test_entry_model.py -v`
Expected: PASS (all tests in the file, including the two new ones).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/entry.py backend/alembic/versions/0010_add_entry_dropped_at_round.py backend/app/schemas/entry.py backend/tests/integration/test_entry_model.py
git commit -m "feat(backend): add Entry.dropped_at_round (FR24)"
```

---

## Task 2: `SwissFormat.generate_round` excludes dropped entries

**Files:**
- Modify: `backend/app/formats/swiss.py`
- Test: `backend/tests/unit/test_swiss_format.py`

**Interfaces:**
- Consumes: `Entry.dropped_at_round` (Task 1).
- Produces: nothing new — `generate_round`'s existing signature/return type (`list[Pairing]`) is unchanged, only its internal pairing-pool selection changes.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/unit/test_swiss_format.py` (extend the existing `_entry()` helper to accept a `dropped_at_round` kwarg):

```python
def _entry(dropped_at_round: int | None = None) -> Entry:
    return Entry(
        id=uuid.uuid4(),
        pod_id=uuid.uuid4(),
        player_uuid=uuid.uuid4(),
        source_system="test",
        metadata_={},
        dropped_at_round=dropped_at_round,
    )


def test_generate_round_excludes_dropped_entries_from_round_one():
    active = [_entry(), _entry(), _entry()]
    dropped = _entry(dropped_at_round=0)
    entries = [*active, dropped]

    pairings = SwissFormat().generate_round(entries=entries, previous_rounds=[])

    paired_ids = {pairing.entry1_id for pairing in pairings} | {
        pairing.entry2_id for pairing in pairings if pairing.entry2_id is not None
    }
    assert dropped.id not in paired_ids
    assert paired_ids == {entry.id for entry in active}


def test_generate_round_excludes_dropped_entries_from_later_rounds():
    active = [_entry(), _entry(), _entry()]
    dropped = _entry(dropped_at_round=1)
    entries = [*active, dropped]

    match_r1 = Match(
        id=uuid.uuid4(),
        entry1_id=active[0].id,
        entry2_id=active[1].id,
        result=MatchResult.ENTRY1_WIN,
    )
    bye_r1 = Match(id=uuid.uuid4(), entry1_id=active[2].id, entry2_id=None)
    dropped_match_r1 = Match(id=uuid.uuid4(), entry1_id=dropped.id, entry2_id=None)
    round_1 = _round(1, [match_r1, bye_r1, dropped_match_r1])

    pairings = SwissFormat().generate_round(entries=entries, previous_rounds=[round_1])

    paired_ids = {pairing.entry1_id for pairing in pairings} | {
        pairing.entry2_id for pairing in pairings if pairing.entry2_id is not None
    }
    assert dropped.id not in paired_ids
```

Note: `dropped_match_r1` above is a bye for the dropped entry, added only so round 1 has an even total of pairings across the 4 entries — this test only asserts on round 2's pool, not round 1's construction.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/unit/test_swiss_format.py -v -k excludes_dropped`
Expected: FAIL — the dropped entry's id appears in `paired_ids` because `generate_round` doesn't filter yet.

- [ ] **Step 3: Filter the pairing pool**

In `backend/app/formats/swiss.py`, modify `generate_round`:

```python
    def generate_round(
        self, entries: Sequence[Entry], previous_rounds: Sequence[Round]
    ) -> list[Pairing]:
        active_entries = [entry for entry in entries if entry.dropped_at_round is None]

        if not previous_rounds:
            return _pair_round_one(active_entries)

        standings, bye_used = _compute_standings(entries, previous_rounds)
        tiebreaks = self.tiebreak.compute(entries, previous_rounds)
        already_paired = _paired_history(previous_rounds)
        ranked = _rank_entries(active_entries, standings, tiebreaks)

        bye_entry = None
        if len(ranked) % 2 == 1:
            bye_entry = _select_bye_entry(ranked, bye_used)
            ranked = [entry for entry in ranked if entry.id != bye_entry.id]

        pairings = _pair_remaining(ranked, already_paired)
        if bye_entry is not None:
            pairings.append(Pairing(entry1_id=bye_entry.id, entry2_id=None))

        return _assign_tables(pairings)
```

(Only the first line — `active_entries = ...` — is new, plus swapping `entries` for `active_entries` in the two `_rank_entries`/`_pair_round_one` call sites. `_compute_standings` and `self.tiebreak.compute` keep receiving the original, unfiltered `entries`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/unit/test_swiss_format.py -v`
Expected: PASS (all tests in the file — confirm no existing test regressed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/formats/swiss.py backend/tests/unit/test_swiss_format.py
git commit -m "feat(backend): exclude dropped entries from Swiss pairing pool (FR24)"
```

---

## Task 3: Round-target math

**Files:**
- Create: `backend/app/formats/round_target.py`
- Test: `backend/tests/unit/test_round_target.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `recommended_rounds(active_entry_count: int) -> int`, consumed by Task 5.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_round_target.py`:

```python
import pytest

from app.formats.round_target import recommended_rounds


@pytest.mark.parametrize(
    ("active_entry_count", "expected"),
    [
        (0, 0),
        (1, 0),
        (2, 1),
        (3, 2),
        (4, 2),
        (5, 3),
        (8, 3),
        (9, 4),
    ],
)
def test_recommended_rounds(active_entry_count, expected):
    assert recommended_rounds(active_entry_count) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/unit/test_round_target.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.formats.round_target'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/formats/round_target.py`:

```python
import math


def recommended_rounds(active_entry_count: int) -> int:
    """ceil(log2(active_entry_count)) — the standard Swiss round-count
    recommendation for a given active (non-dropped) entry count. Returns
    0 for 0 or 1 active entries, where no meaningful round target exists."""
    if active_entry_count <= 1:
        return 0
    return math.ceil(math.log2(active_entry_count))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/unit/test_round_target.py -v`
Expected: PASS (8/8 parametrized cases).

- [ ] **Step 5: Commit**

```bash
git add backend/app/formats/round_target.py backend/tests/unit/test_round_target.py
git commit -m "feat(backend): add recommended_rounds round-target math (FR24)"
```

---

## Task 4: Drop/Undrop API endpoints

**Files:**
- Modify: `backend/app/routers/entries.py`
- Test: `backend/tests/integration/test_entries_api.py`

**Interfaces:**
- Consumes: `Entry.dropped_at_round` (Task 1).
- Produces: `POST /entries/{entry_id}/drop`, `POST /entries/{entry_id}/undrop` — both return `EntryRead`, consumed by Task 6 (frontend API client).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/integration/test_entries_api.py` (reuses the file's existing `_auth_headers`, `_create_pod`, `_create_entry` helpers):

```python
def test_organizer_drops_entry(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    entry_id = _create_entry(api_client, token, pod_id)

    response = api_client.post(f"/entries/{entry_id}/drop", headers=_auth_headers(token))

    assert response.status_code == 200
    assert response.json()["dropped_at_round"] == 0


def test_dropping_already_dropped_entry_is_conflict(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    entry_id = _create_entry(api_client, token, pod_id)
    api_client.post(f"/entries/{entry_id}/drop", headers=_auth_headers(token))

    response = api_client.post(f"/entries/{entry_id}/drop", headers=_auth_headers(token))

    assert response.status_code == 409


def test_non_organizer_cannot_drop_entry(api_client, make_token, db_session):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    entry_id = _create_entry(api_client, token, pod_id)
    reader_token = _add_pod_role_reader_token(db_session, make_token, pod_id)

    response = api_client.post(f"/entries/{entry_id}/drop", headers=_auth_headers(reader_token))

    assert response.status_code == 403


def test_organizer_undrops_entry(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    entry_id = _create_entry(api_client, token, pod_id)
    api_client.post(f"/entries/{entry_id}/drop", headers=_auth_headers(token))

    response = api_client.post(f"/entries/{entry_id}/undrop", headers=_auth_headers(token))

    assert response.status_code == 200
    assert response.json()["dropped_at_round"] is None


def test_undropping_non_dropped_entry_is_conflict(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    entry_id = _create_entry(api_client, token, pod_id)

    response = api_client.post(f"/entries/{entry_id}/undrop", headers=_auth_headers(token))

    assert response.status_code == 409


def test_dropping_entry_in_completed_pod_is_conflict(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    entry_id = _create_entry(api_client, token, pod_id)
    api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))

    response = api_client.post(f"/entries/{entry_id}/drop", headers=_auth_headers(token))

    assert response.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/integration/test_entries_api.py -v -k "drop"`
Expected: FAIL with 404s (routes don't exist yet).

- [ ] **Step 3: Implement the endpoints**

In `backend/app/routers/entries.py`, add `Round` to the existing model import:

```python
from app.models import Entry, Pod, Round
```

Add the two endpoints (after `delete_entry`):

```python
@router.post("/{entry_id}/drop", response_model=EntryRead)
def drop_entry(
    entry_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Entry:
    entry = _get_entry_or_404(db, entry_id)
    pod = db.get(Pod, entry.pod_id)
    _require_pod_event_organizer(
        db, identity, pod, "Organizer role required for this entry's pod's event"
    )
    if entry.dropped_at_round is not None:
        raise HTTPException(status_code=409, detail="entry is already dropped")
    if pod.completed_at is not None:
        raise HTTPException(status_code=409, detail="pod is already complete")

    round_count = db.query(Round).filter_by(pod_id=entry.pod_id).count()
    entry.dropped_at_round = round_count
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/{entry_id}/undrop", response_model=EntryRead)
def undrop_entry(
    entry_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Entry:
    entry = _get_entry_or_404(db, entry_id)
    pod = db.get(Pod, entry.pod_id)
    _require_pod_event_organizer(
        db, identity, pod, "Organizer role required for this entry's pod's event"
    )
    if entry.dropped_at_round is None:
        raise HTTPException(status_code=409, detail="entry is not dropped")

    entry.dropped_at_round = None
    db.commit()
    db.refresh(entry)
    return entry
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/integration/test_entries_api.py -v`
Expected: PASS (all tests in the file, including the 6 new ones).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/entries.py backend/tests/integration/test_entries_api.py
git commit -m "feat(backend): add POST /entries/{id}/drop and /undrop (FR24)"
```

---

## Task 5: `PodReport` gains `active_entry_count`/`recommended_rounds`

**Files:**
- Modify: `backend/app/schemas/report.py`
- Modify: `backend/app/routers/pods.py`
- Test: `backend/tests/integration/test_pods_api.py` (or wherever `get_pod_report` is currently tested — confirm the file name with `grep -rl "pods/.*report\|get_pod_report" backend/tests/integration` before writing; use that file)

**Interfaces:**
- Consumes: `Entry.dropped_at_round` (Task 1), `recommended_rounds()` (Task 3).
- Produces: `PodReport.active_entry_count: int`, `PodReport.recommended_rounds: int`, consumed by Task 6 (frontend API client) and Task 8 (Pairings banner).

- [ ] **Step 1: Find the existing report test file**

Run: `grep -rl "pods/.*report\|get_pod_report" backend/tests/integration`
Use whichever file that prints for the rest of this task's test steps.

- [ ] **Step 2: Write the failing test**

Add to that file (mirror its existing pod/entry/round-creation helpers — likely similar `_create_pod`/`_create_entry` helpers to Task 4's):

```python
def test_report_includes_active_entry_count_and_recommended_rounds(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    entry_ids = [_create_entry(api_client, token, pod_id) for _ in range(4)]

    response = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token))
    body = response.json()
    assert body["active_entry_count"] == 4
    assert body["recommended_rounds"] == 2

    api_client.post(f"/entries/{entry_ids[0]}/drop", headers=_auth_headers(token))

    response = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token))
    body = response.json()
    assert body["active_entry_count"] == 3
    assert body["recommended_rounds"] == 2
```

(If the target file doesn't already define `_auth_headers`/`_create_pod`/`_create_entry`, import or copy them from `test_entries_api.py` — check the file's existing imports first rather than assuming.)

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest <the file from Step 1> -v -k active_entry_count`
Expected: FAIL with `KeyError: 'active_entry_count'` (field doesn't exist on `PodReport` yet).

- [ ] **Step 4: Add the fields to `PodReport`**

In `backend/app/schemas/report.py`, add to `PodReport` (after `is_partial`):

```python
    active_entry_count: int
    recommended_rounds: int
```

- [ ] **Step 5: Compute and return the fields**

In `backend/app/routers/pods.py`, add the import:

```python
from app.formats.round_target import recommended_rounds
```

In `get_pod_report`, add before the `return PodReport(...)`:

```python
    active_entry_count = sum(1 for entry in all_entries if entry.dropped_at_round is None)
```

And add two fields to the `PodReport(...)` constructor call:

```python
    return PodReport(
        is_complete=pod.completed_at is not None,
        rounds_played=len(all_rounds),
        is_partial=is_partial,
        active_entry_count=active_entry_count,
        recommended_rounds=recommended_rounds(active_entry_count),
        standings=[
            StandingRowRead(
                entry_id=row.entry_id,
                points=row.points,
                rank=row.rank,
                tiebreakers=list(row.tiebreakers),
            )
            for row in standings
        ],
    )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest <the file from Step 1> -v`
Expected: PASS (all tests in the file).

- [ ] **Step 7: Run the full backend suite**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS, no regressions (this task touches a shared response schema used elsewhere).

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/report.py backend/app/routers/pods.py <the test file from Step 1>
git commit -m "feat(backend): surface active_entry_count/recommended_rounds on PodReport (FR24)"
```

---

## Task 6: Frontend API client

**Files:**
- Modify: `frontend/src/api/entries.ts`
- Modify: `frontend/src/api/report.ts`
- Test: `frontend/src/api/entries.test.ts` (create if it doesn't exist — check first)

**Interfaces:**
- Consumes: `POST /entries/{id}/drop`, `/undrop` (Task 4), `PodReport`'s new fields (Task 5).
- Produces: `dropEntry(apiFetch, entryId): Promise<EntryRead>`, `undropEntry(apiFetch, entryId): Promise<EntryRead>`, `EntryRead.dropped_at_round: number | null`, `PodReport.active_entry_count: number`, `PodReport.recommended_rounds: number` — consumed by Tasks 7 and 8.

- [ ] **Step 1: Check for an existing entries API test file**

Run: `ls frontend/src/api/entries.test.ts 2>/dev/null || echo "does not exist"`

- [ ] **Step 2: Add `dropped_at_round` to `EntryRead` and the two new functions**

In `frontend/src/api/entries.ts`, add `dropped_at_round: number | null;` to the `EntryRead` interface (after `metadata`), and add after `deleteEntry`:

```typescript
export function dropEntry(apiFetch: ApiFetch, entryId: string): Promise<EntryRead> {
  return apiRequest(apiFetch, `/entries/${entryId}/drop`, { method: "POST" });
}

export function undropEntry(apiFetch: ApiFetch, entryId: string): Promise<EntryRead> {
  return apiRequest(apiFetch, `/entries/${entryId}/undrop`, { method: "POST" });
}
```

- [ ] **Step 3: Add the two new fields to `PodReport`**

In `frontend/src/api/report.ts`, add to the `PodReport` interface (after `is_partial`):

```typescript
  active_entry_count: number;
  recommended_rounds: number;
```

- [ ] **Step 4: Update existing fixtures that construct a full `PodReport`/`EntryRead` object literal**

Run: `grep -rln "is_partial:" frontend/src --include="*.tsx" --include="*.ts"`
For every file that appears (test fixtures constructing a `PodReport`), add `active_entry_count` and `recommended_rounds` to the object literal (pick values consistent with that fixture's existing `standings` array length, e.g. `active_entry_count: standings.length`). Similarly:
Run: `grep -rln "metadata: { display_name" frontend/src --include="*.tsx" --include="*.ts"`
These `EntryRead`-shaped fixtures don't strictly need `dropped_at_round` added (TypeScript structural typing on test fixtures is looser in this codebase's existing patterns — confirm by running the type check in Step 5 first; only add the field to fixtures if the type checker actually flags it as missing).

- [ ] **Step 5: Verify the frontend type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors. Fix any fixture flagged as missing a required field per Step 4's instruction.

- [ ] **Step 6: Run the full frontend test suite**

Run: `cd frontend && npm run test -- --run`
Expected: PASS, no regressions (this task only adds fields/functions, doesn't change existing runtime behavior).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/entries.ts frontend/src/api/report.ts
git commit -m "feat(frontend): add drop/undrop API client + PodReport round-target fields (FR24)"
```

(If Step 4 required fixture edits in other files, `git add` those too before committing.)

---

## Task 7: `EntryRoster` Drop/Undrop UI

**Files:**
- Modify: `frontend/src/routes/EntryRoster.tsx`
- Modify: `frontend/src/routes/EventDetail.tsx`
- Test: `frontend/src/routes/EntryRoster.test.tsx`

**Interfaces:**
- Consumes: `dropEntry`/`undropEntry` (Task 6), `EntryRead.dropped_at_round` (Task 6).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/routes/EntryRoster.test.tsx` (mirror the existing `ASH`/`MISTY` fixtures and the "deletes an entry" test's stateful-handler pattern):

```typescript
  it("drops an entry", async () => {
    let dropped = false;
    server.use(
      http.get("/entries", () =>
        HttpResponse.json([{ ...ASH, dropped_at_round: dropped ? 0 : null }]),
      ),
      http.post("/entries/e1/drop", () => {
        dropped = true;
        return HttpResponse.json({ ...ASH, dropped_at_round: 0 });
      }),
    );

    renderWithProviders(<EntryRoster podId="pod-1" podCompletedAt={null} />);

    fireEvent.click(await screen.findByRole("button", { name: "Drop Ash" }));

    expect(await screen.findByRole("button", { name: "Undrop Ash" })).toBeInTheDocument();
  });

  it("undrops an entry", async () => {
    let dropped = true;
    server.use(
      http.get("/entries", () =>
        HttpResponse.json([{ ...ASH, dropped_at_round: dropped ? 0 : null }]),
      ),
      http.post("/entries/e1/undrop", () => {
        dropped = false;
        return HttpResponse.json({ ...ASH, dropped_at_round: null });
      }),
    );

    renderWithProviders(<EntryRoster podId="pod-1" podCompletedAt={null} />);

    fireEvent.click(await screen.findByRole("button", { name: "Undrop Ash" }));

    expect(await screen.findByRole("button", { name: "Drop Ash" })).toBeInTheDocument();
  });

  it("hides drop/undrop buttons once the pod is complete", async () => {
    server.use(http.get("/entries", () => HttpResponse.json([ASH])));

    renderWithProviders(<EntryRoster podId="pod-1" podCompletedAt="2026-08-11T00:00:00Z" />);

    await screen.findByText("Ash");
    expect(screen.queryByRole("button", { name: "Drop Ash" })).not.toBeInTheDocument();
  });
```

`renderWithProviders`'s real signature is `(element, { path?, routePath?, personaLabel? })` — no `initialPersona` option exists. Omitting the second argument entirely (as above) defaults to the Organizer persona, matching this file's existing "adds an entry as Organizer" test.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test -- --run EntryRoster`
Expected: FAIL — `EntryRoster` doesn't accept a `podCompletedAt` prop yet and has no Drop/Undrop buttons.

- [ ] **Step 3: Add the prop, mutations, and buttons**

In `frontend/src/routes/EntryRoster.tsx`:

Update the import line to add the two new API functions:
```typescript
import { createEntry, deleteEntry, dropEntry, undropEntry, listEntries, updateEntryDisplayName, type EntryRead } from "../api/entries";
```

Update the component signature:
```typescript
export function EntryRoster({ podId, podCompletedAt }: { podId: string; podCompletedAt: string | null }) {
```

Add two mutations alongside the existing `deleteMutation`:
```typescript
  const dropMutation = useMutation({
    mutationFn: (entryId: string) => dropEntry(apiFetch, entryId),
    onSuccess: invalidate,
  });
  const undropMutation = useMutation({
    mutationFn: (entryId: string) => undropEntry(apiFetch, entryId),
    onSuccess: invalidate,
  });
```

Add `dropMutation.error ?? undropMutation.error ??` to the existing `ErrorBanner`'s `error` prop expression.

In the entry row's organizer-only button group (next to the existing Edit/Delete buttons), add:
```typescript
                    {podCompletedAt === null &&
                      (entry.dropped_at_round === null ? (
                        <button
                          aria-label={`Drop ${entry.metadata.display_name ?? entry.id}`}
                          onClick={() => {
                            createMutation.reset();
                            updateMutation.reset();
                            deleteMutation.reset();
                            dropMutation.mutate(entry.id);
                          }}
                        >
                          Drop
                        </button>
                      ) : (
                        <button
                          aria-label={`Undrop ${entry.metadata.display_name ?? entry.id}`}
                          onClick={() => {
                            createMutation.reset();
                            updateMutation.reset();
                            deleteMutation.reset();
                            undropMutation.mutate(entry.id);
                          }}
                        >
                          Undrop
                        </button>
                      ))}
```

- [ ] **Step 4: Update the caller**

In `frontend/src/routes/EventDetail.tsx`, change:
```typescript
          <EntryRoster podId={pod.id} />
```
to:
```typescript
          <EntryRoster podId={pod.id} podCompletedAt={pod.completed_at} />
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm run test -- --run EntryRoster`
Expected: PASS (all tests in the file, including the 3 new ones).

- [ ] **Step 6: Run the full frontend suite**

Run: `cd frontend && npm run test -- --run`
Expected: PASS — confirm `EventDetail.test.tsx` (if it exists and renders `EntryRoster`) doesn't break on the new required prop.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/routes/EntryRoster.tsx frontend/src/routes/EntryRoster.test.tsx frontend/src/routes/EventDetail.tsx
git commit -m "feat(frontend): add Drop/Undrop buttons to EntryRoster (FR24)"
```

---

## Task 8: `Pairings` round-target advisory banner

**Files:**
- Modify: `frontend/src/routes/Pairings.tsx`
- Test: `frontend/src/routes/Pairings.test.tsx`

**Interfaces:**
- Consumes: `fetchPodReport` (already exists in `frontend/src/api/report.ts`), `PodReport.active_entry_count`/`recommended_rounds` (Task 6).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add a `/pods/pod-1/report` handler to every existing test in this file**

Run: `grep -n "server.use(" frontend/src/routes/Pairings.test.tsx`
This prints every `server.use(...)` call site (12, one per `it()` block). In each one, add this handler to the list (alongside the existing `/pods/pod-1/rounds` and `/entries` handlers already there):
```typescript
      http.get("/pods/pod-1/report", () =>
        HttpResponse.json({
          is_complete: false,
          rounds_played: 0,
          is_partial: false,
          active_entry_count: 2,
          recommended_rounds: 1,
          standings: [],
        }),
      ),
```
(`active_entry_count: 2` matches this file's existing `ENTRIES` fixture length; `recommended_rounds: 1` is `ceil(log2(2))`.) Do this for all 12 call sites before writing the new tests below — otherwise every existing test in the file will fail with an unhandled-request error once Task 8's `Pairings.tsx` change lands, since this test setup uses `onUnhandledRequest: "error"`.

- [ ] **Step 2: Write the new failing tests**

This file has a local `renderPairings(personaLabel?)` helper wrapping
`renderWithProviders` with the right `path`/`routePath` already — use it,
not `renderWithProviders` directly. `renderWithProviders` does not expose
its internal `QueryClient`, so a query can only be made to refetch by
triggering a real user action already wired to `invalidateQueries` (e.g.
clicking "Generate Next Round") — there's no way to force-invalidate from
outside the component in a test.

Add to `frontend/src/routes/Pairings.test.tsx`:

```typescript
  it("shows the recommended round count", async () => {
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json([ROUND_1, ROUND_2])),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      http.get("/pods/pod-1/report", () =>
        HttpResponse.json({
          is_complete: false,
          rounds_played: 2,
          is_partial: false,
          active_entry_count: 2,
          recommended_rounds: 1,
          standings: [],
        }),
      ),
    );

    renderPairings();

    expect(await screen.findByText(/Recommended rounds: 1/)).toBeInTheDocument();
  });

  it("shows a banner when the recommended round count changes after generating a round", async () => {
    let rounds: RoundRead[] = [ROUND_1];
    let reportFetchCount = 0;
    server.use(
      http.get("/pods/pod-1/rounds", () => HttpResponse.json(rounds)),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
      http.post("/pods/pod-1/rounds", () => {
        rounds = [...rounds, ROUND_2];
        return HttpResponse.json(ROUND_2, { status: 201 });
      }),
      http.get("/pods/pod-1/report", () => {
        reportFetchCount += 1;
        const active = reportFetchCount === 1 ? 2 : 1;
        return HttpResponse.json({
          is_complete: false,
          rounds_played: rounds.length,
          is_partial: false,
          active_entry_count: active,
          recommended_rounds: active <= 1 ? 0 : 1,
          standings: [],
        });
      }),
    );

    renderPairings();
    await screen.findByText(/Recommended rounds: 1/);

    fireEvent.click(screen.getByRole("button", { name: "Generate Next Round" }));

    expect(await screen.findByText(/Round target changed from 1 to 0/)).toBeInTheDocument();
  });
```

(The second test's `/pods/pod-1/report` handler returns a different
`active_entry_count`/`recommended_rounds` on its second invocation purely
via a closure counter — it doesn't need a real drop to happen, since this
test is only exercising the banner-diffing UI logic, not the drop
feature end-to-end. `Task 4`'s and `Task 5`'s backend tests already cover
the real drop→report-count relationship.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npm run test -- --run Pairings`
Expected: the two new tests FAIL (no round-target text rendered yet); the 12 pre-existing tests should already PASS after Step 1's handler additions — if any of those still fail, the report handler wasn't added correctly to that call site.

- [ ] **Step 4: Implement the banner**

In `frontend/src/routes/Pairings.tsx`, add imports:
```typescript
import { useRef, useState } from "react";
import { fetchPodReport } from "../api/report";
```
(merge `useRef` into the existing `useState` import from `"react"` if one exists — check the current import line first.)

Add a query alongside the existing `roundsQuery`/`entriesQuery`:
```typescript
  const reportQuery = useQuery({
    queryKey: ["report", podId],
    queryFn: () => fetchPodReport(apiFetch, podId),
  });
```

Add `["report", podId]` to the existing `generateMutation`'s `onSuccess` invalidation, so the recommended-rounds figure refreshes whenever a new round is generated (this is also what Task 8's second new test relies on to observe a changed value, since `renderWithProviders` doesn't expose its `QueryClient` for manual invalidation in tests):
```typescript
  const generateMutation = useMutation({
    mutationFn: () => generateRound(apiFetch, podId),
    onSuccess: (newRound) => {
      queryClient.invalidateQueries({ queryKey: ["rounds", podId] });
      queryClient.invalidateQueries({ queryKey: ["report", podId] });
      setSelectedRoundNumber(newRound.number);
    },
  });
```
(Only the new `queryClient.invalidateQueries({ queryKey: ["report", podId] });` line is added — the rest of `generateMutation` is unchanged, shown here for placement context.)

Add banner-diffing state (after the other `useState`/hooks, before the `return`):
```typescript
  const previousRecommendedRounds = useRef<number | null>(null);
  const recommendedRounds = reportQuery.data?.recommended_rounds ?? null;
  const roundTargetChangedFrom =
    recommendedRounds !== null &&
    previousRecommendedRounds.current !== null &&
    previousRecommendedRounds.current !== recommendedRounds
      ? previousRecommendedRounds.current
      : null;
  if (recommendedRounds !== null) {
    previousRecommendedRounds.current = recommendedRounds;
  }
```

Add `reportQuery.error ??` to the existing `ErrorBanner`'s `error` prop expression.

Render the advisory line + banner above the "Generate Next Round" button (inside the `isOrganizer && (...)` block that currently only renders the button, or as its own sibling block right before it):
```typescript
      {reportQuery.data && (
        <p className="mb-2 text-sm text-gray-600">
          Recommended rounds: {reportQuery.data.recommended_rounds} (active entries:{" "}
          {reportQuery.data.active_entry_count})
        </p>
      )}
      {roundTargetChangedFrom !== null && (
        <p className="mb-2 text-sm text-amber-600">
          Round target changed from {roundTargetChangedFrom} to {recommendedRounds}
        </p>
      )}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm run test -- --run Pairings`
Expected: PASS (all 14 tests in the file — 12 pre-existing + 2 new).

- [ ] **Step 6: Run the full frontend suite**

Run: `cd frontend && npm run test -- --run`
Expected: PASS, no regressions elsewhere.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/routes/Pairings.tsx frontend/src/routes/Pairings.test.tsx
git commit -m "feat(frontend): show advisory round-target banner on Pairings (FR24)"
```

---

## Self-Review Notes

- **Spec coverage:** Section 2 (data model) → Task 1. Section 3 (API) → Tasks 4-5. Section 4 (round-target math) → Task 3. Section 5 (frontend) → Tasks 6-8. Section 2's pairing-pool filtering → Task 2.
- **Type/name consistency:** `dropped_at_round` (snake_case, matching the backend/API wire format) used identically in `Entry`, `EntryRead` (backend + frontend), and every test. `recommended_rounds`/`active_entry_count` used identically across `PodReport` (backend + frontend), `recommended_rounds()` the function, and all tests.
- **Task 5's test file location is deliberately looked up at execution time** (Step 1) rather than guessed, since the exact existing test file for `get_pod_report` wasn't confirmed during planning — this is a real unknown flagged for the implementer to resolve with one `grep`, not a placeholder for missing design work.
- **Task 8's Step 1 (updating 12 pre-existing test call sites)** is mechanical but real — flagged explicitly with the exact snippet and a verification step, since skipping it breaks the entire existing test file once the report fetch lands in Task 8 Step 4.
