# Phase 6 — Match & Tournament Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `SwissFormat.generate_round` (built Phase 4, never called from any endpoint) into round-generation endpoints, and add match-result reporting, pod completion, and a standings/placement report — closing GitHub issue #6 (FR17–FR18) and the round-generation gap left by Phases 4–5.

**Architecture:** Two new routers (`app/routers/rounds.py`, `app/routers/matches.py`) plus additions to the existing `app/routers/pods.py`. A new `app/formats/registry.py` mirrors the existing `app/games/registry.py` pattern. `TournamentFormat` gains a `compute_standings` method (abstract, implemented in `SwissFormat`) reused by both the live/final report and the completion check. A new `Pod.completed_at` column (migration `0008`) marks organizer-driven completion. RBAC reuses existing `require_pod_organizer`/`require_pod_access` dependencies plus one new predicate, `pod_staff_allowed` (Organizer or Scorekeeper), following the existing `pod_access_allowed` pattern.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 + Alembic, Pydantic v2, pytest + testcontainers-python (existing — no new dependencies this phase).

**Full design rationale:** `docs/superpowers/specs/2026-08-03-phase-6-match-tournament-reporting-design.md`. Read it if a task's "why" isn't obvious from this plan alone.

## Global Constraints

- Python ≥3.12, FastAPI ≥0.115, SQLAlchemy ≥2.0, Pydantic ≥2.7, Alembic ≥1.13 (existing floors, `backend/pyproject.toml`). No new runtime dependencies this phase.
- TDD (RED → GREEN → REFACTOR) for every task. Integration tests use a real Postgres via `testcontainers-python` (existing `tests/integration/conftest.py` fixtures: `postgres_url`, `migrated_engine`, `db_session`, `api_client`, `make_token`) — never mocked DB.
- `api_client` fixture already wires `get_db_session`/`get_settings` overrides and returns a `TestClient`; `make_token(player_uuid, source_system="club-checkin", roles=None)` mints a valid bearer token. Both come from `tests/integration/conftest.py` — no new fixtures needed this phase.
- Migration files follow the existing hand-written-revision convention in `backend/alembic/versions/000N_*.py` (sequential zero-padded numbers, `revision`/`down_revision` strings, explicit `upgrade()`/`downgrade()`); next number is **`0008`** (`0007_add_pod_event_unique_constraint.py` is the latest).
- Ruff: line-length 100, target `py312` (`backend/pyproject.toml`); all new code must pass `ruff check app tests`.
- `format_slug` is validated only where dereferenced (round generation), never at Pod create/update — same deliberate precedent as `game_slug` (`DECISIONS.md`, "`game_slug` validated at Entry creation, not Pod creation"). Do not add validation to `POST /pods`/`PATCH /pods/{id}`.
- Every PR that adds or changes a route must regenerate `docs/openapi.json` (`cd backend && python scripts/export_openapi.py`) and commit it — `tests/unit/test_openapi_spec.py::test_committed_openapi_spec_matches_generated_spec` fails CI otherwise.
- Never push directly to `main`; never merge without explicit in-the-moment approval, every time.
- This phase is split into **4 sequenced PRs**, each its own branch off `main`, each independently reviewable/testable — matching Phase 5's precedent (`DECISIONS.md`, "Phase 5 split into 4 sequenced PRs"). Issue #6 stays open until PR4 merges. Per `~/.claude/CLAUDE.md`: stop after each PR is opened, run `/review`, do manual verification, and get explicit owner approval before merging — do not chain PRs without a check-in.

---

## PR 1 — Standings/format plumbing, RBAC predicate, `completed_at` column

**Branch:** `feat/phase-6-standings-plumbing` (create off `main` before Task 1). No HTTP routes are added in this PR — pure plumbing, exercised through unit/integration tests directly, same shape as Phase 5 PR1.

### Task 1: `app/formats/registry.py` — tournament format registry

**Files:**
- Create: `backend/app/formats/registry.py`
- Test: `backend/tests/unit/test_formats_registry.py`

**Interfaces:**
- Produces: `app.formats.registry.FORMATS: dict[str, TournamentFormat]`, `app.formats.registry.get_tournament_format(slug: str) -> TournamentFormat`.
- Consumes: `app.formats.swiss.SwissFormat` (existing, Phase 4).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_formats_registry.py
import pytest

from app.formats.registry import get_tournament_format
from app.formats.swiss import SwissFormat


def test_get_tournament_format_returns_swiss_format():
    format_ = get_tournament_format("swiss")

    assert isinstance(format_, SwissFormat)


def test_get_tournament_format_raises_for_unknown_slug():
    with pytest.raises(ValueError, match="unknown tournament format slug"):
        get_tournament_format("single-elim")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_formats_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.formats.registry'`

- [ ] **Step 3: Write `app/formats/registry.py`**

```python
# backend/app/formats/registry.py
from app.formats.base import TournamentFormat
from app.formats.swiss import SwissFormat

FORMATS: dict[str, TournamentFormat] = {
    "swiss": SwissFormat(),
}


def get_tournament_format(slug: str) -> TournamentFormat:
    try:
        return FORMATS[slug]
    except KeyError:
        raise ValueError(f"unknown tournament format slug: {slug!r}") from None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_formats_registry.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/formats/registry.py backend/tests/unit/test_formats_registry.py
git commit -m "feat(formats): add tournament format registry"
```

---

### Task 2: `StandingRow` dataclass + abstract `compute_standings` on `TournamentFormat`

**Files:**
- Modify: `backend/app/formats/base.py`
- Modify: `backend/tests/unit/test_formats.py`

**Interfaces:**
- Produces: `app.formats.base.StandingRow(entry_id: uuid.UUID, points: int, rank: int)` (frozen dataclass); `TournamentFormat.compute_standings(self, entries: Sequence[Entry], rounds: Sequence[Round]) -> list[StandingRow]` (new abstractmethod).
- Consumes: `app.models.Entry`, `app.models.Round` (existing).

**Note:** adding this abstractmethod makes the existing `StubFormat` in `test_formats.py::test_concrete_format_implements_generate_round` abstract-incomplete (it only implements `generate_round`). That test must be updated in the same step that adds the abstractmethod, or it starts failing with `TypeError: Can't instantiate abstract class StubFormat`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/unit/test_formats.py`:

```python
def test_format_missing_compute_standings_cannot_be_instantiated():
    class IncompleteFormat(TournamentFormat):
        slug = "incomplete"

        def generate_round(self, entries, previous_rounds):
            return []

    with pytest.raises(TypeError):
        IncompleteFormat()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_formats.py -v`
Expected: `test_format_missing_compute_standings_cannot_be_instantiated` FAILS (no error raised — `compute_standings` isn't abstract yet). All other tests in the file still PASS at this point.

- [ ] **Step 3: Add `StandingRow` and the abstractmethod, and fix the pre-existing `StubFormat`**

`backend/app/formats/base.py` (full file):

```python
import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from app.models import Entry, Round


@dataclass(frozen=True)
class Pairing:
    entry1_id: uuid.UUID
    entry2_id: uuid.UUID | None  # None means a bye
    table_number: int | None = None


@dataclass(frozen=True)
class StandingRow:
    entry_id: uuid.UUID
    points: int
    rank: int


class TournamentFormat(ABC):
    slug: str

    @abstractmethod
    def generate_round(
        self, entries: Sequence[Entry], previous_rounds: Sequence[Round]
    ) -> list[Pairing]:
        """Return this pod's next round's pairings given its entries and completed prior rounds."""

    @abstractmethod
    def compute_standings(
        self, entries: Sequence[Entry], rounds: Sequence[Round]
    ) -> list[StandingRow]:
        """Return ranked standings for all entries given completed rounds."""
```

In `backend/tests/unit/test_formats.py`, update the *existing* `StubFormat` in `test_concrete_format_implements_generate_round` to also implement `compute_standings` (otherwise it can no longer be instantiated):

```python
def test_concrete_format_implements_generate_round():
    class StubFormat(TournamentFormat):
        slug = "stub"

        def generate_round(self, entries, previous_rounds):
            return [Pairing(entry1_id=uuid.uuid4(), entry2_id=None)]

        def compute_standings(self, entries, rounds):
            return []

    pairings = StubFormat().generate_round(entries=[], previous_rounds=[])

    assert len(pairings) == 1
    assert pairings[0].entry2_id is None
```

- [ ] **Step 4: Run the full file to verify everything passes**

Run: `cd backend && pytest tests/unit/test_formats.py -v`
Expected: PASS (all tests, including the new one and the fixed `StubFormat` test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/formats/base.py backend/tests/unit/test_formats.py
git commit -m "feat(formats): add StandingRow and abstract compute_standings"
```

---

### Task 3: `SwissFormat.compute_standings`

**Files:**
- Modify: `backend/app/formats/swiss.py`
- Test: `backend/tests/unit/test_swiss_format.py`

**Interfaces:**
- Produces: `SwissFormat.compute_standings(entries, rounds) -> list[StandingRow]` — ranked 1-indexed, same points (3/1/0) and same UUID-string tiebreak as the existing internal pairing order. Re-raises the existing `_compute_standings` `ValueError` unchanged (any unreported non-bye match in the given rounds).
- Consumes: `_compute_standings`, `_rank_entries` (existing private helpers in this module, unchanged), `app.formats.base.StandingRow` (Task 2).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/unit/test_swiss_format.py`:

```python
def test_compute_standings_ranks_by_points_descending():
    e1, e2, e3, e4 = _entry(), _entry(), _entry(), _entry()
    round1 = _round(
        1,
        [
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e1.id,
                entry2_id=e2.id,
                result=MatchResult.ENTRY1_WIN,
            ),
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e3.id,
                entry2_id=e4.id,
                result=MatchResult.TIE,
            ),
        ],
    )

    standings = SwissFormat().compute_standings([e1, e2, e3, e4], [round1])

    assert [row.entry_id for row in standings][0] == e1.id
    assert [row.points for row in standings] == [3, 1, 1, 0]
    assert [row.rank for row in standings] == [1, 2, 3, 4]


def test_compute_standings_with_no_rounds_ranks_all_entries_at_zero_points():
    e1, e2 = _entry(), _entry()

    standings = SwissFormat().compute_standings([e1, e2], [])

    assert {row.points for row in standings} == {0}
    assert sorted(row.rank for row in standings) == [1, 2]


def test_compute_standings_raises_on_unreported_match():
    e1, e2 = _entry(), _entry()
    round1 = _round(
        1,
        [
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e1.id,
                entry2_id=e2.id,
                result=MatchResult.UNREPORTED,
            )
        ],
    )

    with pytest.raises(ValueError, match="unreported"):
        SwissFormat().compute_standings([e1, e2], [round1])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_swiss_format.py -v`
Expected: FAIL — `AttributeError: 'SwissFormat' object has no attribute 'compute_standings'`

- [ ] **Step 3: Implement `compute_standings`**

In `backend/app/formats/swiss.py`, add the import and method:

```python
from app.formats.base import Pairing, StandingRow, TournamentFormat
```

(replaces the existing `from app.formats.base import Pairing, TournamentFormat` line)

Add to the `SwissFormat` class, after `generate_round`:

```python
    def compute_standings(
        self, entries: Sequence[Entry], rounds: Sequence[Round]
    ) -> list[StandingRow]:
        standings, _ = _compute_standings(entries, rounds)
        ranked = _rank_entries(entries, standings)
        return [
            StandingRow(entry_id=entry.id, points=standings.get(entry.id, 0), rank=i + 1)
            for i, entry in enumerate(ranked)
        ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_swiss_format.py -v`
Expected: PASS (all tests, old and new)

- [ ] **Step 5: Commit**

```bash
git add backend/app/formats/swiss.py backend/tests/unit/test_swiss_format.py
git commit -m "feat(formats): implement SwissFormat.compute_standings"
```

---

### Task 4: `pod_staff_allowed` RBAC predicate (Organizer or Scorekeeper)

**Files:**
- Modify: `backend/app/auth/dependencies.py`
- Test: `backend/tests/integration/test_auth_dependencies.py`

**Interfaces:**
- Produces: `app.auth.dependencies.pod_staff_allowed(db: Session, identity: Identity, pod_id: uuid.UUID) -> bool` — `True` iff the identity is an Organizer for the pod's event, or holds a `PodRoleName.SCOREKEEPER` role on the pod. Mirrors the existing `pod_access_allowed` predicate exactly (same file, same shape), one level more restrictive (excludes plain `PodRoleName.USER`).
- Consumes: `event_organizer_exists`, `PodRole`, `PodRoleName` (existing, same file/module).

**Note:** no new `require_pod_staff` FastAPI path-dependency is added — nothing needs one yet. `POST /matches/{match_id}/result` (PR3) has no `pod_id` in its path (`pod_id` comes from `match.round.pod_id`), so it calls `pod_staff_allowed` directly and raises its own `HTTPException(403)`, the same idiom `app/routers/entries.py`'s `_require_pod_event_organizer` already uses for the same reason.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/integration/test_auth_dependencies.py` (needs `PodRoleName` added to the existing `from app.models.rbac import EventOrganizer, PodRole` import, and `pod_staff_allowed` added to the existing `from app.auth.dependencies import (...)` import block):

```python
def test_pod_staff_allowed_true_for_event_organizer(db_session):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    player_uuid = uuid.uuid4()
    db_session.add(
        EventOrganizer(event_id=event.id, player_uuid=player_uuid, source_system="club-checkin")
    )
    db_session.commit()
    identity = Identity(player_uuid=player_uuid, source_system="club-checkin", has_organizer_claim=False)

    assert pod_staff_allowed(db_session, identity, pod.id) is True


def test_pod_staff_allowed_true_for_scorekeeper(db_session):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    player_uuid = uuid.uuid4()
    db_session.add(
        PodRole(
            pod_id=pod.id,
            player_uuid=player_uuid,
            source_system="club-checkin",
            role=PodRoleName.SCOREKEEPER,
        )
    )
    db_session.commit()
    identity = Identity(player_uuid=player_uuid, source_system="club-checkin", has_organizer_claim=False)

    assert pod_staff_allowed(db_session, identity, pod.id) is True


def test_pod_staff_allowed_false_for_plain_user_role(db_session):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    player_uuid = uuid.uuid4()
    db_session.add(
        PodRole(
            pod_id=pod.id,
            player_uuid=player_uuid,
            source_system="club-checkin",
            role=PodRoleName.USER,
        )
    )
    db_session.commit()
    identity = Identity(player_uuid=player_uuid, source_system="club-checkin", has_organizer_claim=False)

    assert pod_staff_allowed(db_session, identity, pod.id) is False


def test_pod_staff_allowed_false_for_nonexistent_pod(db_session):
    identity = Identity(player_uuid=uuid.uuid4(), source_system="club-checkin", has_organizer_claim=False)

    assert pod_staff_allowed(db_session, identity, uuid.uuid4()) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/integration/test_auth_dependencies.py -v -k pod_staff_allowed`
Expected: FAIL — `ImportError: cannot import name 'pod_staff_allowed'`

- [ ] **Step 3: Implement `pod_staff_allowed`**

In `backend/app/auth/dependencies.py`, update the import line:

```python
from app.models.rbac import EventOrganizer, PodRole, PodRoleName
```

Add the function, next to `pod_access_allowed`:

```python
def pod_staff_allowed(db: Session, identity: Identity, pod_id: uuid.UUID) -> bool:
    pod = db.get(Pod, pod_id)
    if pod is None:
        return False
    if event_organizer_exists(db, identity, pod.event_id):
        return True
    return (
        db.query(PodRole)
        .filter_by(
            pod_id=pod_id,
            player_uuid=identity.player_uuid,
            source_system=identity.source_system,
            role=PodRoleName.SCOREKEEPER,
        )
        .first()
        is not None
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/integration/test_auth_dependencies.py -v -k pod_staff_allowed`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full dependencies test file to confirm no regressions, then commit**

Run: `cd backend && pytest tests/integration/test_auth_dependencies.py -v`
Expected: PASS (all tests)

```bash
git add backend/app/auth/dependencies.py backend/tests/integration/test_auth_dependencies.py
git commit -m "feat(auth): add pod_staff_allowed RBAC predicate (Organizer or Scorekeeper)"
```

---

### Task 5: `Pod.completed_at` column (migration `0008`)

**Files:**
- Create: `backend/alembic/versions/0008_add_pod_completed_at.py`
- Modify: `backend/app/models/pod.py`
- Modify: `backend/app/schemas/pod.py`
- Test: `backend/tests/integration/test_pod_model.py`

**Interfaces:**
- Produces: `Pod.completed_at: Mapped[datetime | None]` (nullable, no default); `PodRead.completed_at: datetime | None` (API-visible).
- Consumes: nothing new.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/integration/test_pod_model.py` (needs `from datetime import date` already imported; add `func` import from sqlalchemy for the second test):

```python
def test_pod_completed_at_defaults_to_none(db_session):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()

    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.commit()

    assert pod.completed_at is None


def test_pod_completed_at_can_be_set(db_session):
    from sqlalchemy import func

    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.commit()

    pod.completed_at = func.now()
    db_session.commit()
    db_session.refresh(pod)

    assert pod.completed_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/integration/test_pod_model.py -v -k completed_at`
Expected: FAIL — `AttributeError: 'Pod' object has no attribute 'completed_at'` (or `TypeError` from the constructor call in the fixture-shared `Pod(...)` calls elsewhere failing to matter here — the new attribute simply doesn't exist yet)

- [ ] **Step 3: Add the migration**

```python
# backend/alembic/versions/0008_add_pod_completed_at.py
"""add completed_at to pods

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-03

"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pods", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("pods", "completed_at")
```

- [ ] **Step 4: Add the model column**

`backend/app/models/pod.py` (full file):

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Pod(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "pods"
    __table_args__ = (UniqueConstraint("event_id", name="uq_pod_event"),)

    event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("events.id"), nullable=False
    )
    format_slug: Mapped[str] = mapped_column(nullable=False)
    game_slug: Mapped[str] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 5: Add the schema field**

`backend/app/schemas/pod.py` (full file):

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PodCreate(BaseModel):
    event_id: uuid.UUID
    format_slug: str
    game_slug: str


class PodUpdate(BaseModel):
    format_slug: str
    game_slug: str


class PodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    format_slug: str
    game_slug: str
    completed_at: datetime | None
```

- [ ] **Step 6: Run the migration against the test DB and run tests**

Run: `cd backend && pytest tests/integration/test_pod_model.py -v`
Expected: PASS (all tests — `migrated_engine` runs `alembic upgrade head` automatically each session)

- [ ] **Step 7: Run the full backend suite to confirm no regressions**

Run: `cd backend && pytest -v`
Expected: PASS (all tests — this closes out PR1)

- [ ] **Step 8: Commit**

```bash
git add backend/alembic/versions/0008_add_pod_completed_at.py backend/app/models/pod.py backend/app/schemas/pod.py backend/tests/integration/test_pod_model.py
git commit -m "feat(pods): add completed_at column"
```

- [ ] **Step 9: Open PR1**

```bash
git push -u origin feat/phase-6-standings-plumbing
gh pr create --title "Phase 6 PR1: standings/format plumbing, RBAC predicate, completed_at column" --body "$(cat <<'EOF'
## Summary
- `app/formats/registry.py`: tournament format lookup, mirrors `app/games/registry.py`
- `TournamentFormat.compute_standings` (abstract) + `SwissFormat.compute_standings` implementation
- `pod_staff_allowed` RBAC predicate (Organizer or Scorekeeper)
- `Pod.completed_at` column (migration 0008)

No new HTTP routes — pure plumbing for PR2-4. Part of Phase 6 (issue #6).

## Test plan
- [ ] `pytest` full suite passes
EOF
)"
```

**STOP.** Run `/review`, do manual verification per `~/.claude/CLAUDE.md`, wait for explicit owner approval before merging. Do not proceed to PR2 until PR1 is merged and its branch cleaned up.

---

## PR 2 — Round generation endpoints

**Branch:** `feat/phase-6-round-generation` (off `main`, after PR1 is merged).

### Task 6: `RoundRead`/`MatchRead` schemas

**Files:**
- Create: `backend/app/schemas/round.py`
- Create: `backend/app/schemas/match.py`

**Interfaces:**
- Produces: `app.schemas.match.MatchRead` (id, round_id, entry1_id, entry2_id, result, reported_by, witnessed_by, table_number); `app.schemas.round.RoundRead` (id, pod_id, number, matches: list[MatchRead]).
- Consumes: `app.models.MatchResult` (existing).

- [ ] **Step 1: Write `app/schemas/match.py`**

```python
# backend/app/schemas/match.py
import uuid

from pydantic import BaseModel, ConfigDict

from app.models import MatchResult


class MatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    round_id: uuid.UUID
    entry1_id: uuid.UUID
    entry2_id: uuid.UUID | None
    result: MatchResult
    reported_by: str | None
    witnessed_by: str | None
    table_number: int | None
```

- [ ] **Step 2: Write `app/schemas/round.py`**

```python
# backend/app/schemas/round.py
import uuid

from pydantic import BaseModel, ConfigDict

from app.schemas.match import MatchRead


class RoundRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pod_id: uuid.UUID
    number: int
    matches: list[MatchRead]
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/round.py backend/app/schemas/match.py
git commit -m "feat(schemas): add RoundRead and MatchRead"
```

(No standalone test for these — they're exercised end-to-end by Task 7's integration tests. Pydantic schemas with no logic of their own don't need unit tests per this codebase's existing convention: compare `app/schemas/entry.py`/`pod_role.py`, neither has a dedicated schema test file.)

---

### Task 7: `app/routers/rounds.py` — `POST`/`GET /pods/{pod_id}/rounds`

**Files:**
- Create: `backend/app/routers/rounds.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_rounds_api.py`

**Interfaces:**
- Produces: `POST /pods/{pod_id}/rounds` (201, `RoundRead`), `GET /pods/{pod_id}/rounds` (200, `list[RoundRead]`).
- Consumes: `require_pod_organizer`, `require_pod_access` (existing, `app/auth/dependencies.py`); `get_tournament_format` (Task 1); `app.models.Entry`, `Match`, `Pod`, `Round` (existing); `app.schemas.round.RoundRead` (Task 6).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integration/test_rounds_api.py
import uuid


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_pod(api_client, token, format_slug="swiss") -> str:
    event_id = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    ).json()["id"]
    return api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": format_slug, "game_slug": "generic"},
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


def test_organizer_generates_round_one(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    _add_entry(api_client, token, pod_id)

    response = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    assert response.status_code == 201
    body = response.json()
    assert body["number"] == 1
    assert len(body["matches"]) == 1
    assert body["matches"][0]["entry2_id"] is not None


def test_non_organizer_cannot_generate_round(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)
    _add_entry(api_client, owner_token, pod_id)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(stranger_token))

    assert response.status_code == 403


def test_round_generation_rejects_empty_pod(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)

    response = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    assert response.status_code == 409


def test_round_generation_rejects_unrecognized_format_slug(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token, format_slug="single-elim")
    _add_entry(api_client, token, pod_id)

    response = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    assert response.status_code == 422


def test_round_generation_blocked_until_prior_round_fully_reported(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    _add_entry(api_client, token, pod_id)
    api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    response = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    assert response.status_code == 409


def test_organizer_can_list_rounds_with_nested_matches(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    _add_entry(api_client, token, pod_id)
    api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    response = api_client.get(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert len(body[0]["matches"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/integration/test_rounds_api.py -v`
Expected: FAIL — `404 Not Found` on `POST /pods/{pod_id}/rounds` (route doesn't exist yet)

- [ ] **Step 3: Write `app/routers/rounds.py`**

```python
# backend/app/routers/rounds.py
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_pod_access, require_pod_organizer
from app.auth.identity import Identity
from app.db import get_db_session
from app.formats.registry import get_tournament_format
from app.models import Entry, Match, Pod, Round
from app.schemas.round import RoundRead

router = APIRouter(prefix="/pods/{pod_id}/rounds", tags=["rounds"])


def _get_pod_or_404(db: Session, pod_id: uuid.UUID) -> Pod:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    return pod


@router.post("", response_model=RoundRead, status_code=201)
def generate_round(
    pod_id: uuid.UUID,
    identity: Identity = Depends(require_pod_organizer),
    db: Session = Depends(get_db_session),
) -> Round:
    pod = _get_pod_or_404(db, pod_id)

    try:
        tournament_format = get_tournament_format(pod.format_slug)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"pod's format_slug {pod.format_slug!r} is not a recognized tournament format",
        ) from exc

    entries = db.query(Entry).filter_by(pod_id=pod_id).order_by(Entry.id).all()
    if not entries:
        raise HTTPException(status_code=409, detail="pod has no entries")

    previous_rounds = db.query(Round).filter_by(pod_id=pod_id).order_by(Round.number).all()

    try:
        pairings = tournament_format.generate_round(
            entries=entries, previous_rounds=previous_rounds
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    round_ = Round(pod_id=pod_id, number=len(previous_rounds) + 1)
    db.add(round_)
    db.flush()

    for pairing in pairings:
        db.add(
            Match(
                round_id=round_.id,
                entry1_id=pairing.entry1_id,
                entry2_id=pairing.entry2_id,
                table_number=pairing.table_number,
            )
        )
    db.commit()
    db.refresh(round_)
    return round_


@router.get("", response_model=list[RoundRead])
def list_rounds(
    pod_id: uuid.UUID,
    identity: Identity = Depends(require_pod_access),
    db: Session = Depends(get_db_session),
) -> list[Round]:
    _get_pod_or_404(db, pod_id)
    return db.query(Round).filter_by(pod_id=pod_id).order_by(Round.number).all()
```

- [ ] **Step 4: Wire the router into `app/main.py`**

```python
# backend/app/main.py
from app.routers import entries, events, pod_roles, pods, rounds
```

(replaces the existing `from app.routers import entries, events, pod_roles, pods` line)

```python
app.include_router(rounds.router)
```

(add after the existing `app.include_router(pod_roles.router)` line)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/integration/test_rounds_api.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Run the full backend suite to confirm no regressions**

Run: `cd backend && pytest -v`
Expected: PASS (all tests)

- [ ] **Step 7: Regenerate and commit the OpenAPI spec**

Run: `cd backend && python scripts/export_openapi.py`

```bash
git add backend/app/routers/rounds.py backend/app/main.py backend/tests/integration/test_rounds_api.py docs/openapi.json
git commit -m "feat(rounds): add round generation and listing endpoints"
```

- [ ] **Step 8: Open PR2**

```bash
git push -u origin feat/phase-6-round-generation
gh pr create --title "Phase 6 PR2: round generation endpoints" --body "$(cat <<'EOF'
## Summary
- POST /pods/{pod_id}/rounds: generate the next Swiss round (Organizer-only)
- GET /pods/{pod_id}/rounds: list rounds with nested matches

Part of Phase 6 (issue #6). Depends on PR1 (merged).

## Test plan
- [ ] `pytest` full suite passes
- [ ] Manual: curl POST/GET against staging
EOF
)"
```

**STOP.** Run `/review`, manual verification, explicit owner approval before merging.

---

## PR 3 — Match result reporting

**Branch:** `feat/phase-6-match-reporting` (off `main`, after PR2 is merged).

### Task 8: `MatchResultUpdate` schema

**Files:**
- Modify: `backend/app/schemas/match.py`

**Interfaces:**
- Produces: `app.schemas.match.MatchResultUpdate(result: Literal[MatchResult.ENTRY1_WIN, MatchResult.ENTRY2_WIN, MatchResult.TIE])` — a `Literal` restricted to the three reportable outcomes means Pydantic itself rejects `"unreported"` (or any other value) with a 422, no custom validator needed.

- [ ] **Step 1: Add the schema**

`backend/app/schemas/match.py` (full file):

```python
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models import MatchResult


class MatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    round_id: uuid.UUID
    entry1_id: uuid.UUID
    entry2_id: uuid.UUID | None
    result: MatchResult
    reported_by: str | None
    witnessed_by: str | None
    table_number: int | None


class MatchResultUpdate(BaseModel):
    result: Literal[MatchResult.ENTRY1_WIN, MatchResult.ENTRY2_WIN, MatchResult.TIE]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/match.py
git commit -m "feat(schemas): add MatchResultUpdate"
```

(Exercised end-to-end by Task 9's integration tests, same rationale as Task 6.)

---

### Task 9: `app/routers/matches.py` — `POST /matches/{match_id}/result`

**Files:**
- Create: `backend/app/routers/matches.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/integration/test_matches_api.py`

**Interfaces:**
- Produces: `POST /matches/{match_id}/result` (200, `MatchRead`).
- Consumes: `get_current_identity` (existing); `pod_staff_allowed` (Task 4); `app.models.Match`, `Round` (existing); `app.schemas.match.MatchRead`, `MatchResultUpdate` (Task 6, Task 8).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/integration/test_matches_api.py
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


def _pod_with_one_match(api_client, token):
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    _add_entry(api_client, token, pod_id)
    round_ = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    return pod_id, round_["matches"][0]["id"]


def test_organizer_reports_match_result(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    _, match_id = _pod_with_one_match(api_client, token)

    response = api_client.post(
        f"/matches/{match_id}/result", json={"result": "entry1_win"}, headers=_auth_headers(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "entry1_win"
    assert body["reported_by"] == body["witnessed_by"]
    assert body["reported_by"] is not None


def test_scorekeeper_can_report_match_result(api_client, make_token):
    organizer_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id, match_id = _pod_with_one_match(api_client, organizer_token)
    scorekeeper_uuid = uuid.uuid4()
    api_client.post(
        f"/pods/{pod_id}/roles",
        json={
            "player_uuid": str(scorekeeper_uuid),
            "source_system": "club-checkin",
            "role": "scorekeeper",
        },
        headers=_auth_headers(organizer_token),
    )
    scorekeeper_token = make_token(player_uuid=scorekeeper_uuid, source_system="club-checkin")

    response = api_client.post(
        f"/matches/{match_id}/result",
        json={"result": "tie"},
        headers=_auth_headers(scorekeeper_token),
    )

    assert response.status_code == 200


def test_plain_user_role_cannot_report_match_result(api_client, make_token):
    organizer_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id, match_id = _pod_with_one_match(api_client, organizer_token)
    player_uuid = uuid.uuid4()
    api_client.post(
        f"/pods/{pod_id}/roles",
        json={
            "player_uuid": str(player_uuid),
            "source_system": "club-checkin",
            "role": "user",
        },
        headers=_auth_headers(organizer_token),
    )
    player_token = make_token(player_uuid=player_uuid, source_system="club-checkin")

    response = api_client.post(
        f"/matches/{match_id}/result",
        json={"result": "entry1_win"},
        headers=_auth_headers(player_token),
    )

    assert response.status_code == 403


def test_reporting_unreported_as_result_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    _, match_id = _pod_with_one_match(api_client, token)

    response = api_client.post(
        f"/matches/{match_id}/result",
        json={"result": "unreported"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_reporting_a_bye_match_result_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    round_ = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    bye_match_id = round_["matches"][0]["id"]

    response = api_client.post(
        f"/matches/{bye_match_id}/result",
        json={"result": "entry1_win"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 409


def test_reporting_result_for_unknown_match_is_not_found(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.post(
        f"/matches/{uuid.uuid4()}/result",
        json={"result": "entry1_win"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/integration/test_matches_api.py -v`
Expected: FAIL — `404 Not Found` on `POST /matches/{match_id}/result` (route doesn't exist yet)

- [ ] **Step 3: Write `app/routers/matches.py`**

```python
# backend/app/routers/matches.py
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_identity, pod_staff_allowed
from app.auth.identity import Identity
from app.db import get_db_session
from app.models import Match, Round
from app.schemas.match import MatchRead, MatchResultUpdate

router = APIRouter(prefix="/matches", tags=["matches"])


def _get_match_or_404(db: Session, match_id: uuid.UUID) -> Match:
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="match not found")
    return match


def _require_pod_staff(db: Session, identity: Identity, pod_id: uuid.UUID) -> None:
    """Check Organizer-or-Scorekeeper for the given pod; raise HTTPException(403) if lacking."""
    if not pod_staff_allowed(db, identity, pod_id):
        raise HTTPException(status_code=403, detail="Organizer or Scorekeeper role required")


@router.post("/{match_id}/result", response_model=MatchRead)
def report_match_result(
    match_id: uuid.UUID,
    payload: MatchResultUpdate,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Match:
    match = _get_match_or_404(db, match_id)
    round_ = db.get(Round, match.round_id)
    _require_pod_staff(db, identity, round_.pod_id)

    if match.entry2_id is None:
        raise HTTPException(status_code=409, detail="bye matches do not require a result")

    reporter = f"{identity.source_system}:{identity.player_uuid}"
    match.result = payload.result
    match.reported_by = reporter
    match.witnessed_by = reporter
    db.commit()
    db.refresh(match)
    return match
```

- [ ] **Step 4: Wire the router into `app/main.py`**

```python
# backend/app/main.py
from app.routers import entries, events, matches, pod_roles, pods, rounds
```

(replaces the Task 7 import line)

```python
app.include_router(matches.router)
```

(add after `app.include_router(rounds.router)`)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/integration/test_matches_api.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Run the full backend suite to confirm no regressions**

Run: `cd backend && pytest -v`
Expected: PASS (all tests)

- [ ] **Step 7: Regenerate and commit the OpenAPI spec**

Run: `cd backend && python scripts/export_openapi.py`

```bash
git add backend/app/routers/matches.py backend/app/main.py backend/tests/integration/test_matches_api.py docs/openapi.json
git commit -m "feat(matches): add match result reporting endpoint"
```

- [ ] **Step 8: Open PR3**

```bash
git push -u origin feat/phase-6-match-reporting
gh pr create --title "Phase 6 PR3: match result reporting endpoint" --body "$(cat <<'EOF'
## Summary
- POST /matches/{match_id}/result: Organizer-or-Scorekeeper reports a BO1 result.
  reported_by/witnessed_by both set from the caller's identity (both roles
  qualify as witness, per owner decision during Phase 6 brainstorming).

Part of Phase 6 (issue #6). Depends on PR2 (merged).

## Test plan
- [ ] `pytest` full suite passes
- [ ] Manual: curl as Organizer and as Scorekeeper against staging
EOF
)"
```

**STOP.** Run `/review`, manual verification, explicit owner approval before merging.

---

## PR 4 — Pod completion + standings report

**Branch:** `feat/phase-6-completion-report` (off `main`, after PR3 is merged).

### Task 10: `PodReport`/`StandingRowRead` schemas

**Files:**
- Create: `backend/app/schemas/report.py`

**Interfaces:**
- Produces: `app.schemas.report.StandingRowRead(entry_id: uuid.UUID, points: int, rank: int)`; `app.schemas.report.PodReport(is_complete: bool, rounds_played: int, is_partial: bool, standings: list[StandingRowRead])`.

- [ ] **Step 1: Write the schema**

```python
# backend/app/schemas/report.py
import uuid

from pydantic import BaseModel


class StandingRowRead(BaseModel):
    entry_id: uuid.UUID
    points: int
    rank: int


class PodReport(BaseModel):
    is_complete: bool
    rounds_played: int
    is_partial: bool
    standings: list[StandingRowRead]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/report.py
git commit -m "feat(schemas): add PodReport and StandingRowRead"
```

(Exercised end-to-end by Task 12's integration tests, same rationale as Task 6.)

---

### Task 11: `POST /pods/{pod_id}/complete`

**Files:**
- Modify: `backend/app/routers/pods.py`
- Test: `backend/tests/integration/test_pods_api.py`

**Interfaces:**
- Produces: `_round_fully_reported(round_: Round) -> bool` (module-private helper in `pods.py`, also consumed by Task 12); `POST /pods/{pod_id}/complete` (200, `PodRead`).
- Consumes: `require_pod_organizer` (existing); `app.models.MatchResult`, `Round` (existing); `sqlalchemy.func` (for `func.now()`).

**Design note:** completion is always the organizer's explicit call — this phase has no round-target concept (dynamic target recalculation from drops is deferred, see `DECISIONS.md` and `REQUIREMENTS.md` FR24). The only structural precondition is that the *last* round (if any exist) has no unreported non-bye matches — by construction, round generation (PR2) never lets an earlier round be incomplete while a later one exists, so checking only the last round is sufficient, not a simplification that misses cases.

- [ ] **Step 1: Write the failing tests**

`test_pods_api.py` already has `_auth_headers` and `_create_event` (used by every existing test, which inline their own `POST /pods` call rather than sharing a helper) — it has **no** `_create_pod` or `_add_entry` helper yet. Add both, then the new tests:

```python
def _create_pod(api_client, token) -> str:
    event_id = _create_event(api_client, token)
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


def test_organizer_completes_pod_with_no_rounds(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)

    response = api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))

    assert response.status_code == 200
    assert response.json()["completed_at"] is not None


def test_completing_already_complete_pod_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))

    response = api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))

    assert response.status_code == 409


def test_completing_pod_with_unreported_match_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    _add_entry(api_client, token, pod_id)
    api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    response = api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))

    assert response.status_code == 409


def test_non_organizer_cannot_complete_pod(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(stranger_token))

    assert response.status_code == 403
```

These two helpers are local to `test_pods_api.py`, distinct from (but shaped identically to) the ones already written in `test_rounds_api.py` (Task 7) and `test_matches_api.py` (Task 9) — this codebase duplicates small per-file test helpers rather than sharing them across test files (compare `test_pod_roles_api.py`'s `_create_pod` vs `test_rounds_api.py`'s own copy), so this is consistent with existing practice, not a new pattern.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/integration/test_pods_api.py -v -k complete`
Expected: FAIL — `404 Not Found` on `POST /pods/{pod_id}/complete` (route doesn't exist yet)

- [ ] **Step 3: Add the endpoint and helper to `app/routers/pods.py`**

Update the top of `backend/app/routers/pods.py` — two lines change in the existing import block:

```python
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
```

(replaces the existing `from sqlalchemy.exc import IntegrityError` / `from sqlalchemy.orm import Session` pair — adds the `func` import)

```python
from app.models import Entry, Match, MatchResult, Pod, Round
```

(replaces the existing `from app.models import Entry, Match, Pod, Round` line — adds `MatchResult`)

Add the helper and endpoint (after `update_pod`, before `delete_pod_children`):

```python
def _round_fully_reported(round_: Round) -> bool:
    return all(
        match.entry2_id is None or match.result != MatchResult.UNREPORTED
        for match in round_.matches
    )


@router.post("/{pod_id}/complete", response_model=PodRead)
def complete_pod(
    pod_id: uuid.UUID,
    identity: Identity = Depends(require_pod_organizer),
    db: Session = Depends(get_db_session),
) -> Pod:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    if pod.completed_at is not None:
        raise HTTPException(status_code=409, detail="pod already complete")

    rounds = db.query(Round).filter_by(pod_id=pod_id).order_by(Round.number).all()
    if rounds and not _round_fully_reported(rounds[-1]):
        raise HTTPException(
            status_code=409,
            detail=f"round {rounds[-1].number} has an unreported match; cannot complete pod",
        )

    pod.completed_at = func.now()
    db.commit()
    db.refresh(pod)
    return pod
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/integration/test_pods_api.py -v -k complete`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full backend suite to confirm no regressions**

Run: `cd backend && pytest -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/pods.py backend/tests/integration/test_pods_api.py
git commit -m "feat(pods): add pod completion endpoint"
```

---

### Task 12: `GET /pods/{pod_id}/report`

**Files:**
- Modify: `backend/app/routers/pods.py`
- Test: `backend/tests/integration/test_pods_api.py`

**Interfaces:**
- Produces: `GET /pods/{pod_id}/report` (200, `PodReport`).
- Consumes: `require_pod_access` (existing); `get_tournament_format` (Task 1); `_round_fully_reported` (Task 11, same file); `app.schemas.report.PodReport`, `StandingRowRead` (Task 10).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/integration/test_pods_api.py`:

```python
def test_report_is_empty_for_pod_with_no_entries(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)

    response = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "is_complete": False,
        "rounds_played": 0,
        "is_partial": False,
        "standings": [],
    }


def test_report_reflects_reported_results(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    _add_entry(api_client, token, pod_id)
    round_ = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    match_id = round_["matches"][0]["id"]
    api_client.post(
        f"/matches/{match_id}/result", json={"result": "entry1_win"}, headers=_auth_headers(token)
    )

    response = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["is_partial"] is False
    assert body["rounds_played"] == 1
    assert body["standings"][0]["points"] == 3
    assert body["standings"][0]["rank"] == 1


def test_report_is_partial_when_current_round_has_unreported_matches(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    _add_entry(api_client, token, pod_id)
    api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    response = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["is_partial"] is True
    assert body["rounds_played"] == 1
    # Round 1 itself is excluded from standings (it's the in-progress round being
    # partial-filtered out) — both entries still appear, at 0 points each, not an
    # empty list: compute_standings still runs over the (empty) usable_rounds and
    # all entries, it just has no completed-round results to award points from.
    assert len(body["standings"]) == 2
    assert {row["points"] for row in body["standings"]} == {0}


def test_report_marks_is_complete_after_pod_completion(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))

    response = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token))

    assert response.json()["is_complete"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/integration/test_pods_api.py -v -k report`
Expected: FAIL — `404 Not Found` on `GET /pods/{pod_id}/report` (route doesn't exist yet)

- [ ] **Step 3: Add the endpoint to `app/routers/pods.py`**

Add two new import lines: `from app.formats.registry import get_tournament_format` goes *before* the existing `from app.games.registry import get_game_module` line (alphabetical: `formats` < `games`); `from app.schemas.report import PodReport, StandingRowRead` goes after the existing `from app.schemas.pod import ...` line (alphabetical: `pod` < `report`). Ruff's import sort (`ruff check --fix`) will also catch and fix ordering if this is off.

```python
from app.formats.registry import get_tournament_format
from app.games.registry import get_game_module
from app.models import Entry, Match, MatchResult, Pod, Round
from app.models.rbac import PodRole
from app.schemas.pod import PodCreate, PodRead, PodUpdate
from app.schemas.report import PodReport, StandingRowRead
```

(full `app.*` import block after this task, for reference)

Add the endpoint (after `complete_pod`):

```python
@router.get("/{pod_id}/report", response_model=PodReport)
def get_pod_report(
    pod_id: uuid.UUID,
    identity: Identity = Depends(require_pod_access),
    db: Session = Depends(get_db_session),
) -> PodReport:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")

    try:
        tournament_format = get_tournament_format(pod.format_slug)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"pod's format_slug {pod.format_slug!r} is not a recognized tournament format",
        ) from exc

    all_entries = db.query(Entry).filter_by(pod_id=pod_id).order_by(Entry.id).all()
    all_rounds = db.query(Round).filter_by(pod_id=pod_id).order_by(Round.number).all()

    usable_rounds = all_rounds
    is_partial = False
    if usable_rounds and not _round_fully_reported(usable_rounds[-1]):
        usable_rounds = usable_rounds[:-1]
        is_partial = True

    standings = tournament_format.compute_standings(all_entries, usable_rounds)

    return PodReport(
        is_complete=pod.completed_at is not None,
        rounds_played=len(all_rounds),
        is_partial=is_partial,
        standings=[
            StandingRowRead(entry_id=row.entry_id, points=row.points, rank=row.rank)
            for row in standings
        ],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/integration/test_pods_api.py -v -k report`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full backend suite to confirm no regressions**

Run: `cd backend && pytest -v`
Expected: PASS (all tests)

- [ ] **Step 6: Regenerate and commit the OpenAPI spec**

Run: `cd backend && python scripts/export_openapi.py`

```bash
git add backend/app/routers/pods.py backend/tests/integration/test_pods_api.py docs/openapi.json
git commit -m "feat(pods): add standings/placement report endpoint"
```

- [ ] **Step 7: Open PR4**

```bash
git push -u origin feat/phase-6-completion-report
gh pr create --title "Phase 6 PR4: pod completion + standings report" --body "$(cat <<'EOF'
## Summary
- POST /pods/{pod_id}/complete: Organizer marks a pod finished (blocked if the
  last round has unreported matches)
- GET /pods/{pod_id}/report: live/final standings, points + UUID-tiebreak rank,
  is_partial when the current round is still in progress

Closes issue #6 (FR17-FR18). Depends on PR3 (merged). This is the final PR of
Phase 6 — after merge, close issue #6.

## Test plan
- [ ] `pytest` full suite passes
- [ ] Manual: curl full flow against staging — create pod, add entries, generate
      round 1, report result, generate round 2, complete pod, view report
EOF
)"
```

**STOP.** Run `/review`, manual verification per `~/.claude/CLAUDE.md` (full flow: setup → round generation → scoring → completion → report), explicit owner approval before merging. After merge, close issue #6 and clean up branches (remote + local) for all four PRs if not already done.

---

## Self-Review Notes

- **Spec coverage:** every endpoint in the design spec's table (round generation, round listing, match result, pod completion, report) has a task. `format_slug` validation deliberately matches the `game_slug` precedent (Global Constraints), correcting an error in the original design doc draft. The `require_pod_staff` FastAPI-dependency named in the design spec was replaced with a plain `pod_staff_allowed` predicate + local raise-helper (Task 4/9) — no path-scoped caller exists for a dependency version, and the codebase's own `entries.py` precedent (`_require_pod_event_organizer`) already establishes this exact local-helper idiom for the same reason (pod_id not in the route's own path).
- **Placeholder scan:** no TBD/TODO markers; every step has real code.
- **Type consistency:** `StandingRow`/`StandingRowRead` fields (`entry_id`, `points`, `rank`) match across Task 2 (dataclass), Task 3 (producer), and Task 10/12 (schema + router construction). `pod_staff_allowed` signature matches its Task 4 definition and Task 9 caller exactly. `_round_fully_reported` is defined once (Task 11) and reused by Task 12, not redefined.
- **Test-fixture accuracy:** caught and fixed two real bugs during self-review, before execution: (1) Task 11/12's tests originally assumed `_create_pod`/`_add_entry` helpers already existed in `test_pods_api.py` — confirmed by reading the file that they don't (it only inlines pod creation per-test) — now added explicitly in Task 11. (2) Task 12's `test_report_is_partial_when_current_round_has_unreported_matches` originally asserted `standings == []` for a partial report with 2 entries and zero fully-reported rounds — wrong, `compute_standings` still runs over all entries with zero results, yielding 2 rows at 0 points each, not an empty list. Fixed.
