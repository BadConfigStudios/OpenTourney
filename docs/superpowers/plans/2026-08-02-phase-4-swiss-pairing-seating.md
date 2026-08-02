# Phase 4 — Swiss Pairing/Round Generation + Seating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Swiss `TournamentFormat` (per-round loop, pairings driven by prior results/standings) and table/seat assignment for in-person pairings, behind the Phase 3 `TournamentFormat.generate_round(entries, previous_rounds) -> list[Pairing]` interface. Closes GitHub issue #4 (FR10, FR11).

**Architecture:** Pure-Python Swiss algorithm in `backend/app/formats/swiss.py` — no DB access, no FastAPI endpoints (those are Phase 5). Standings are computed from `Round.matches` (a new ORM relationship added this phase, since Phase 3 didn't need one). Table/seat numbers are carried on both `Match` (persisted column) and `Pairing` (the format's output dataclass).

**Tech Stack:** SQLAlchemy 2.0 (relationship + new migration), Alembic, pytest. No new dependencies.

## Global Constraints

- Python 3.12, SQLAlchemy 2.0 declarative style only (`Mapped[...]` / `mapped_column`), matches `backend/pyproject.toml` `requires-python`.
- Postgres 16 dialect types (`postgresql.dialects.UUID`, `JSONB`) — this project targets Postgres only.
- No hardcoded secrets — N/A this phase (no new env-dependent code).
- TDD (RED → GREEN → REFACTOR): write the failing test, confirm it fails, write minimal code to pass, confirm it passes, commit test + implementation (+ migration where applicable) together.
- Commits: Conventional Commits format, trailer `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`, stage files by exact name (never `-A`/`.`).
- `app.formats` and `app.games` stay fully decoupled (NFR5) — this phase only touches `app.formats`.
- SQLAlchemy `mapped_column(default=...)` fires at flush/INSERT time, **not** at object construction — unit tests that build transient `Match`/`Round`/`Entry` objects without a DB session must explicitly pass every field the test logic reads (notably `result=` on `Match`), never rely on the column default being populated.
- One PR for this whole phase, description says `Closes #4`.

---

### Task 1: `Round.matches` relationship

**Files:**
- Modify: `backend/app/models/round.py`
- Test: `backend/tests/integration/test_round_match_models.py`

**Interfaces:**
- Produces: `Round.matches: Mapped[list[Match]]` — a live SQLAlchemy relationship (FK already exists on `Match.round_id`, added Phase 3). No migration needed (ORM-only, additive).
- Consumes: `app.models.Match` (Phase 3), existing `db_session` fixture (Phase 3, `backend/tests/integration/conftest.py`).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/integration/test_round_match_models.py`:

```python
def test_round_matches_relationship_returns_associated_matches(db_session):
    pod, entry1, entry2 = _make_pod_with_two_entries(db_session)
    round_ = Round(pod_id=pod.id, number=1)
    db_session.add(round_)
    db_session.flush()

    match = Match(round_id=round_.id, entry1_id=entry1.id, entry2_id=entry2.id)
    db_session.add(match)
    db_session.commit()
    db_session.refresh(round_)

    assert [m.id for m in round_.matches] == [match.id]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && pytest tests/integration/test_round_match_models.py::test_round_matches_relationship_returns_associated_matches -v`
Expected: FAIL (`AttributeError: 'Round' object has no attribute 'matches'`)

- [ ] **Step 3: Add the relationship**

`backend/app/models/round.py` (full file):

```python
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.match import Match


class Round(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "rounds"
    __table_args__ = (UniqueConstraint("pod_id", "number", name="uq_round_number_per_pod"),)

    pod_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("pods.id"), nullable=False
    )
    number: Mapped[int] = mapped_column(nullable=False)
    matches: Mapped[list["Match"]] = relationship(order_by="Match.id")
```

`Match` isn't imported directly (avoids a circular import with `app/models/match.py`); the `TYPE_CHECKING` import satisfies the type checker and the `"Match"` string lets SQLAlchemy resolve the class lazily via the mapper registry.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && pytest tests/integration/test_round_match_models.py -v`
Expected: PASS (all tests in the file, including the new one and the five from Phase 3)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/round.py backend/tests/integration/test_round_match_models.py
git commit -m "$(cat <<'EOF'
feat(domain): add Round.matches relationship

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `table_number` on `Match` and `Pairing`

**Files:**
- Modify: `backend/app/models/match.py`
- Modify: `backend/app/formats/base.py`
- Create: `backend/alembic/versions/0005_add_match_table_number.py`
- Test: `backend/tests/integration/test_round_match_models.py`
- Test: `backend/tests/unit/test_formats.py`

**Interfaces:**
- Produces: `Match.table_number: Mapped[int | None]` (persisted, nullable). `Pairing.table_number: int | None` (dataclass field, default `None`, appended after existing fields so existing `Pairing(entry1_id=..., entry2_id=...)` call sites keep working).
- Consumes: nothing new — extends Phase 3's `Match` and `Pairing`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/integration/test_round_match_models.py`:

```python
def test_match_persists_table_number(db_session):
    pod, entry1, entry2 = _make_pod_with_two_entries(db_session)
    round_ = Round(pod_id=pod.id, number=1)
    db_session.add(round_)
    db_session.flush()

    match = Match(round_id=round_.id, entry1_id=entry1.id, entry2_id=entry2.id, table_number=7)
    db_session.add(match)
    db_session.commit()

    fetched = db_session.get(Match, match.id)
    assert fetched.table_number == 7


def test_match_table_number_defaults_to_null(db_session):
    pod, entry1, entry2 = _make_pod_with_two_entries(db_session)
    round_ = Round(pod_id=pod.id, number=1)
    db_session.add(round_)
    db_session.flush()

    match = Match(round_id=round_.id, entry1_id=entry1.id, entry2_id=None)
    db_session.add(match)
    db_session.commit()

    fetched = db_session.get(Match, match.id)
    assert fetched.table_number is None
```

Append to `backend/tests/unit/test_formats.py`:

```python
def test_pairing_table_number_defaults_to_none():
    pairing = Pairing(entry1_id=uuid.uuid4(), entry2_id=uuid.uuid4())

    assert pairing.table_number is None


def test_pairing_table_number_can_be_set():
    pairing = Pairing(entry1_id=uuid.uuid4(), entry2_id=uuid.uuid4(), table_number=3)

    assert pairing.table_number == 3
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/integration/test_round_match_models.py tests/unit/test_formats.py -v`
Expected: FAIL (`TypeError: 'table_number' is an invalid keyword argument for Match` / for `Pairing`)

- [ ] **Step 3: Add `table_number` to `Match`**

In `backend/app/models/match.py`, add after the `confirmed_by` column:

```python
    table_number: Mapped[int | None] = mapped_column(nullable=True)
```

- [ ] **Step 4: Add `table_number` to `Pairing`**

In `backend/app/formats/base.py`, update the dataclass:

```python
@dataclass(frozen=True)
class Pairing:
    entry1_id: uuid.UUID
    entry2_id: uuid.UUID | None  # None means a bye
    table_number: int | None = None
```

- [ ] **Step 5: Write the migration**

`backend/alembic/versions/0005_add_match_table_number.py`:

```python
"""add table_number to matches

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-02

"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("table_number", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "table_number")
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && pytest tests/integration/test_round_match_models.py tests/unit/test_formats.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/match.py backend/app/formats/base.py \
  backend/alembic/versions/0005_add_match_table_number.py \
  backend/tests/integration/test_round_match_models.py backend/tests/unit/test_formats.py
git commit -m "$(cat <<'EOF'
feat(domain): add table_number to Match and Pairing

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `SwissFormat` — round 1 pairing + table assignment

**Files:**
- Create: `backend/app/formats/swiss.py`
- Test: `backend/tests/unit/test_swiss_format.py`

**Interfaces:**
- Produces: `app.formats.swiss.SwissFormat` (`slug = "swiss"`, implements `TournamentFormat`). Module-level helper `_assign_tables(pairings: list[Pairing]) -> list[Pairing]` (sequential 1-based table numbers for non-bye pairings, in list order; byes keep `table_number=None`) — used by every later task in this file.
- Consumes: `app.formats.base.Pairing`, `app.formats.base.TournamentFormat` (Task 2), `app.models.Entry` (Phase 3).

- [ ] **Step 1: Write the failing tests**

`backend/tests/unit/test_swiss_format.py`:

```python
import uuid

from app.formats.swiss import SwissFormat
from app.models import Entry


def _entry() -> Entry:
    return Entry(
        id=uuid.uuid4(),
        pod_id=uuid.uuid4(),
        player_uuid=uuid.uuid4(),
        source_system="test",
        metadata_={},
    )


def test_round_one_pairs_entries_sequentially_with_table_numbers():
    entries = [_entry(), _entry(), _entry(), _entry()]

    pairings = SwissFormat().generate_round(entries=entries, previous_rounds=[])

    assert len(pairings) == 2
    assert pairings[0].entry1_id == entries[0].id
    assert pairings[0].entry2_id == entries[1].id
    assert pairings[0].table_number == 1
    assert pairings[1].entry1_id == entries[2].id
    assert pairings[1].entry2_id == entries[3].id
    assert pairings[1].table_number == 2


def test_round_one_gives_bye_to_last_entry_when_odd():
    entries = [_entry(), _entry(), _entry()]

    pairings = SwissFormat().generate_round(entries=entries, previous_rounds=[])

    assert len(pairings) == 2
    bye = pairings[-1]
    assert bye.entry1_id == entries[2].id
    assert bye.entry2_id is None
    assert bye.table_number is None


def test_round_one_with_no_entries_returns_no_pairings():
    pairings = SwissFormat().generate_round(entries=[], previous_rounds=[])

    assert pairings == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/unit/test_swiss_format.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.formats.swiss'`)

- [ ] **Step 3: Write the implementation**

`backend/app/formats/swiss.py`:

```python
from collections.abc import Sequence

from app.formats.base import Pairing, TournamentFormat
from app.models import Entry, Round

WIN_POINTS = 3
TIE_POINTS = 1
LOSS_POINTS = 0


class SwissFormat(TournamentFormat):
    slug = "swiss"

    def generate_round(
        self, entries: Sequence[Entry], previous_rounds: Sequence[Round]
    ) -> list[Pairing]:
        if not previous_rounds:
            return _pair_round_one(entries)

        raise NotImplementedError("subsequent-round pairing lands in Task 4/5")


def _pair_round_one(entries: Sequence[Entry]) -> list[Pairing]:
    ordered = list(entries)
    pairings: list[Pairing] = []
    i = 0
    while i + 1 < len(ordered):
        pairings.append(Pairing(entry1_id=ordered[i].id, entry2_id=ordered[i + 1].id))
        i += 2
    if i < len(ordered):
        pairings.append(Pairing(entry1_id=ordered[i].id, entry2_id=None))
    return _assign_tables(pairings)


def _assign_tables(pairings: list[Pairing]) -> list[Pairing]:
    assigned: list[Pairing] = []
    table_number = 1
    for pairing in pairings:
        if pairing.entry2_id is None:
            assigned.append(pairing)
            continue
        assigned.append(
            Pairing(
                entry1_id=pairing.entry1_id,
                entry2_id=pairing.entry2_id,
                table_number=table_number,
            )
        )
        table_number += 1
    return assigned
```

The `raise NotImplementedError` branch is deliberate — Task 4/5 replace it. Round 1 is fully working and tested by this task alone.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/unit/test_swiss_format.py -v`
Expected: PASS (all three tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/formats/swiss.py backend/tests/unit/test_swiss_format.py
git commit -m "$(cat <<'EOF'
feat(formats): add SwissFormat round-1 pairing and table assignment

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Standings computation + unreported-match guard

**Files:**
- Modify: `backend/app/formats/swiss.py`
- Test: `backend/tests/unit/test_swiss_format.py`

**Interfaces:**
- Produces: module-level `_compute_standings(entries: Sequence[Entry], previous_rounds: Sequence[Round]) -> tuple[dict[uuid.UUID, int], set[uuid.UUID]]` — returns `(points_by_entry_id, entry_ids_that_have_used_a_bye)`. Raises `ValueError` if any non-bye match in `previous_rounds` has `result == MatchResult.UNREPORTED`.
- Consumes: `app.models.MatchResult` (Phase 3), `Round.matches` (Task 1).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/unit/test_swiss_format.py`:

```python
import pytest

from app.formats.swiss import _compute_standings
from app.models import Match, MatchResult, Round


def _round(number: int, matches: list[Match]) -> Round:
    round_ = Round(id=uuid.uuid4(), pod_id=uuid.uuid4(), number=number)
    round_.matches = matches
    return round_


def test_compute_standings_awards_win_tie_loss_points():
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

    standings, bye_used = _compute_standings([e1, e2, e3, e4], [round1])

    assert standings[e1.id] == 3
    assert standings[e2.id] == 0
    assert standings[e3.id] == 1
    assert standings[e4.id] == 1
    assert bye_used == set()


def test_compute_standings_counts_bye_as_a_win():
    e1 = _entry()
    round1 = _round(
        1, [Match(id=uuid.uuid4(), round_id=uuid.uuid4(), entry1_id=e1.id, entry2_id=None)]
    )

    standings, bye_used = _compute_standings([e1], [round1])

    assert standings[e1.id] == 3
    assert bye_used == {e1.id}


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
        _compute_standings([e1, e2], [round1])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/unit/test_swiss_format.py -v`
Expected: FAIL (`ImportError: cannot import name '_compute_standings'`)

- [ ] **Step 3: Write the implementation**

In `backend/app/formats/swiss.py`, add the import and function:

```python
from app.models import Entry, MatchResult, Round
```

(replaces the existing `from app.models import Entry, Round` line)

```python
def _compute_standings(
    entries: Sequence[Entry], previous_rounds: Sequence[Round]
) -> tuple[dict, set]:
    standings = {entry.id: 0 for entry in entries}
    bye_used = set()

    for round_ in previous_rounds:
        for match in round_.matches:
            if match.entry2_id is None:
                standings[match.entry1_id] = standings.get(match.entry1_id, 0) + WIN_POINTS
                bye_used.add(match.entry1_id)
                continue

            if match.result is MatchResult.UNREPORTED:
                raise ValueError(
                    f"round {round_.number} has an unreported match; "
                    "cannot generate the next round"
                )
            if match.result is MatchResult.ENTRY1_WIN:
                standings[match.entry1_id] = standings.get(match.entry1_id, 0) + WIN_POINTS
            elif match.result is MatchResult.ENTRY2_WIN:
                standings[match.entry2_id] = standings.get(match.entry2_id, 0) + WIN_POINTS
            else:
                standings[match.entry1_id] = standings.get(match.entry1_id, 0) + TIE_POINTS
                standings[match.entry2_id] = standings.get(match.entry2_id, 0) + TIE_POINTS

    return standings, bye_used
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/unit/test_swiss_format.py -v`
Expected: PASS (all tests, including Task 3's)

- [ ] **Step 5: Commit**

```bash
git add backend/app/formats/swiss.py backend/tests/unit/test_swiss_format.py
git commit -m "$(cat <<'EOF'
feat(formats): compute Swiss standings from prior-round results

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Subsequent-round pairing — score groups, rematch avoidance, bye rotation

**Files:**
- Modify: `backend/app/formats/swiss.py`
- Test: `backend/tests/unit/test_swiss_format.py`

**Interfaces:**
- Produces: `SwissFormat.generate_round` fully implemented for `previous_rounds` non-empty (replaces Task 3's `NotImplementedError` branch). Module-level helpers `_paired_history`, `_rank_entries`, `_select_bye_entry`, `_pair_remaining` (all consumed only within `swiss.py`, but `_select_bye_entry` is tested directly).
- Consumes: `_compute_standings` (Task 4), `_assign_tables` (Task 3).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/unit/test_swiss_format.py`:

```python
def test_round_two_pairs_within_score_groups_by_prior_results():
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
                result=MatchResult.ENTRY1_WIN,
            ),
        ],
    )

    pairings = SwissFormat().generate_round(entries=[e1, e2, e3, e4], previous_rounds=[round1])

    pair_sets = {frozenset({p.entry1_id, p.entry2_id}) for p in pairings}
    assert pair_sets == {frozenset({e1.id, e3.id}), frozenset({e2.id, e4.id})}
    assert all(p.table_number is not None for p in pairings)


def test_round_three_avoids_rematches_across_two_prior_rounds():
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
                result=MatchResult.ENTRY1_WIN,
            ),
        ],
    )
    round2 = _round(
        2,
        [
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e1.id,
                entry2_id=e3.id,
                result=MatchResult.ENTRY1_WIN,
            ),
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e2.id,
                entry2_id=e4.id,
                result=MatchResult.ENTRY2_WIN,
            ),
        ],
    )

    pairings = SwissFormat().generate_round(
        entries=[e1, e2, e3, e4], previous_rounds=[round1, round2]
    )

    pair_sets = {frozenset({p.entry1_id, p.entry2_id}) for p in pairings}
    already_played = {
        frozenset({e1.id, e2.id}),
        frozenset({e3.id, e4.id}),
        frozenset({e1.id, e3.id}),
        frozenset({e2.id, e4.id}),
    }
    assert pair_sets.isdisjoint(already_played)
    assert pair_sets == {frozenset({e1.id, e4.id}), frozenset({e2.id, e3.id})}


def test_select_bye_entry_skips_lowest_ranked_if_already_used():
    from app.formats.swiss import _select_bye_entry

    e1, e2 = _entry(), _entry()
    ranked = [e1, e2]  # e2 is lowest-ranked (last in the list)
    bye_used = {e2.id}

    chosen = _select_bye_entry(ranked, bye_used)

    assert chosen.id == e1.id
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/unit/test_swiss_format.py -v`
Expected: FAIL (`ImportError: cannot import name '_select_bye_entry'`, and the two `generate_round` tests fail with `NotImplementedError`)

- [ ] **Step 3: Write the implementation**

In `backend/app/formats/swiss.py`, replace the `SwissFormat.generate_round` body:

```python
    def generate_round(
        self, entries: Sequence[Entry], previous_rounds: Sequence[Round]
    ) -> list[Pairing]:
        if not previous_rounds:
            return _pair_round_one(entries)

        standings, bye_used = _compute_standings(entries, previous_rounds)
        already_paired = _paired_history(previous_rounds)
        ranked = _rank_entries(entries, standings)

        bye_entry = None
        if len(ranked) % 2 == 1:
            bye_entry = _select_bye_entry(ranked, bye_used)
            ranked = [entry for entry in ranked if entry.id != bye_entry.id]

        pairings = _pair_remaining(ranked, already_paired)
        if bye_entry is not None:
            pairings.append(Pairing(entry1_id=bye_entry.id, entry2_id=None))

        return _assign_tables(pairings)
```

Add the new helpers (after `_compute_standings`):

```python
def _paired_history(previous_rounds: Sequence[Round]) -> set:
    paired = set()
    for round_ in previous_rounds:
        for match in round_.matches:
            if match.entry2_id is not None:
                paired.add(frozenset({match.entry1_id, match.entry2_id}))
    return paired


def _rank_entries(entries: Sequence[Entry], standings: dict) -> list:
    return sorted(entries, key=lambda entry: (-standings.get(entry.id, 0), str(entry.id)))


def _select_bye_entry(ranked: list, bye_used: set):
    for entry in reversed(ranked):
        if entry.id not in bye_used:
            return entry
    return ranked[-1]


def _pair_remaining(ranked: list, already_paired: set) -> list[Pairing]:
    remaining = list(ranked)
    pairings: list[Pairing] = []

    while remaining:
        entry1 = remaining.pop(0)
        partner_index = next(
            (
                i
                for i, candidate in enumerate(remaining)
                if frozenset({entry1.id, candidate.id}) not in already_paired
            ),
            0,
        )
        entry2 = remaining.pop(partner_index)
        pairings.append(Pairing(entry1_id=entry1.id, entry2_id=entry2.id))

    return pairings
```

`_pair_remaining` is only ever called with an even-length `ranked` list — `generate_round` removes the bye entry first when the count is odd — so `remaining` is never empty at the point `entry1` is popped.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/unit/test_swiss_format.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && pytest -v`
Expected: PASS (all unit + integration tests, Phase 3 and Phase 4 combined)

- [ ] **Step 6: Commit**

```bash
git add backend/app/formats/swiss.py backend/tests/unit/test_swiss_format.py
git commit -m "$(cat <<'EOF'
feat(formats): pair subsequent Swiss rounds from standings, avoid rematches

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Document Phase 4 technical decisions

**Files:**
- Modify: `DECISIONS.md`

**Interfaces:** none — documentation only.

- [ ] **Step 1: Append decision entries**

Add to the end of `DECISIONS.md`:

```markdown
## 2026-08-02 — `Round.matches` ORM relationship, not an interface signature change

`TournamentFormat.generate_round(entries, previous_rounds)` needs prior
match results to compute standings, but `Round` had no relationship to
`Match` (Phase 3 didn't need one). Rather than change the already-merged
interface signature to carry results explicitly, Phase 4 adds a standard
SQLAlchemy `relationship()` from `Round` to `Match` (the FK already exists
on `Match.round_id`). `previous_rounds: Sequence[Round]` stays exactly as
documented; Swiss reads `round.matches`. No migration needed — additive,
ORM-only change.

## 2026-08-02 — Table/seat assignment: `table_number` on `Match`/`Pairing`, not a separate entity

FR11 only requires a table/seat number attached to each in-person pairing.
Adding `table_number: int | None` directly to `Match` (migration `0005`)
and to the `Pairing` dataclass in `app.formats.base` matches the existing
one-pairing-per-match shape. A separate `Seat`/`Table` entity would add
schema complexity (multi-entry tables, table metadata) that nothing in
v1 scope requires.

## 2026-08-02 — Swiss scoring: 3/1/0 match points, byes count as a win

Standard Play!-style Swiss scoring (win = 3, tie = 1, loss = 0; a bye
scores as a win) drives standings for round 2+. Round 1 pairs entries in
the order passed to `generate_round` (sequential adjacent pairing,
odd-one-out gets the bye) rather than randomizing internally — any
randomization is the caller's responsibility (e.g. shuffling `entries`
before calling), keeping the format itself deterministic and easy to
test.
```

- [ ] **Step 2: Commit**

```bash
git add DECISIONS.md
git commit -m "$(cat <<'EOF'
docs: record Phase 4 technical decisions

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Verify migration `0005` on real `opentourney-staging` Postgres

No code changes — this is NFR3 ("every phase verified against real Kubernetes staging environment"). Run by whoever executes the mandatory manual-verification gate before merge.

**Files:** none.

- [ ] **Step 1: Find the staging Postgres connection secret**

```bash
kubectl get secrets -n opentourney-staging | grep pguser
```

- [ ] **Step 2: Get the connection URI and the primary service name**

```bash
kubectl get secret -n opentourney-staging <secret-name-from-step-1> -o jsonpath='{.data.uri}' | base64 -d
kubectl get svc -n opentourney-staging
```

- [ ] **Step 3: Port-forward to the primary Postgres service**

```bash
kubectl port-forward -n opentourney-staging svc/<primary-service-name> 5433:5432
```

- [ ] **Step 4: Run the migration against staging, pointed at the forwarded port**

In a second terminal, rewrite the host:port from the Step 2 `uri` to `localhost:5433` and export it:

```bash
cd backend
export DATABASE_URL="postgresql+psycopg://<user>:<password>@localhost:5433/opentourney"
python -m alembic upgrade head
```

Expected: Alembic reports upgrading `-> 0005` with no errors (already at `0004` from Phase 3's verification).

- [ ] **Step 5: Confirm the column exists**

```bash
psql "$DATABASE_URL" -c '\d matches'
```

Expected: `table_number | integer |` listed among the columns.

- [ ] **Step 6: Tear down the port-forward**

Stop the `kubectl port-forward` process (Ctrl-C). No commit for this task — it's verification only, recorded in the PR description / manual-verification checklist.

---

## Self-Review Notes

- **Spec coverage**: FR10 "full Swiss `TournamentFormat` implementation (per-round loop, pairings depend on prior results)" → Tasks 3–5 (round 1 in Task 3, standings in Task 4, subsequent-round pairing/rematch-avoidance/bye-rotation in Task 5). FR11 "table/seat assignment for in-person pairings" → Task 2 (schema) + Task 3 (`_assign_tables`, exercised in every `generate_round` call). Issue #4's five acceptance criteria: "Swiss `TournamentFormat` implementation behind the Phase 3 interface" → Task 3 `SwissFormat` class; "Round 1 pairings generated from Pod entries" → Task 3; "Subsequent rounds generated from prior-round results/standings" → Task 4–5; "Table/seat assignment included in pairing output" → Task 2–3; "Unit tests cover pairing correctness across multiple rounds" → Task 5's round-2/round-3 tests plus Task 3's round-1 tests. NFR3 (staging verification) → Task 7.
- **Placeholder scan**: no TBD/TODO markers. Task 3's `raise NotImplementedError` is intentional scaffolding replaced by name in Task 5, not a placeholder left unresolved by plan's end.
- **Type consistency**: `Pairing(entry1_id, entry2_id, table_number=None)` defined once in Task 2 and used identically in Tasks 3 and 5. `SwissFormat.generate_round(entries: Sequence[Entry], previous_rounds: Sequence[Round]) -> list[Pairing]` matches the Phase 3 `TournamentFormat` ABC signature exactly — no interface break. `_compute_standings` return type `tuple[dict[uuid.UUID, int], set[uuid.UUID]]` (Task 4) is consumed with matching unpacking (`standings, bye_used = ...`) in Task 5.
