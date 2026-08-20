# Phase 18 — Pokémon Tiebreak Strategy + Head-to-Head Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement FR28 (Pokémon Op Win%/Op Op Win% tiebreak strategy) and FR29 (head-to-head pairwise fallback tiebreaker), and fold in issue #57 (labeled/typed tiebreak wire contract), per the approved design at `docs/superpowers/specs/2026-08-20-phase18-pokemon-tiebreak-headtohead-design.md`.

**Architecture:** Extract `OwpOomwTiebreak`'s shared point/opponent-tallying helpers into `app/tiebreak/_shared.py`; add a second `TiebreakStrategy` implementation (`PokemonTiebreak`) with its own floor/cap/bye-denominator rules and a pairwise `break_tie()` head-to-head fallback; wire game-to-tiebreak selection through a new `GameModule.tiebreak_strategy()` method and a new `app/ruleset.py` factory; extend `_rank_entries` with a grouping pass that invokes `break_tie()` for exactly-2 tied entries; change the report wire contract from bare `list[float]` to labeled `list[TiebreakValue]`; validate the whole chain against two real, anonymized TOM tournament exports already committed to this branch.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic (backend), Vite + React + Vitest (frontend), pytest, Python stdlib `xml.etree.ElementTree` for the TOM fixture parser (no new dependency).

## Global Constraints

- `PokemonTiebreak` floor: `0.25` (handbook §5.3.3.1).
- `PokemonTiebreak` cap: `1.0` if `entry.dropped_at_round is None`, else `0.75`. Cap applied before floor: `max(floor, min(cap, raw))`.
- Bye round: counts as a win in the numerator, excluded from the rounds-played denominator (handbook §5.6.1) — implemented via `_shared.points_and_rounds_played(..., bye_rounds_played=False)`.
- `PokemonTiebreak.compute()` returns a 2-tuple `(Op Win%, Op Op Win%)`; `labels()` returns `("Op Win%", "Op Op Win%")`.
- `OwpOomwTiebreak.labels()` returns `("OMW%", "OOMW%")`; its own math is unchanged by the `_shared.py` extraction.
- `break_tie(entry_a_id, entry_b_id, rounds) -> int | None` returns `-1` if `entry_a_id` ranks higher, `1` if `entry_b_id` ranks higher, `None` if unresolved (no match between them, a tie between them, or the base class's no-op default).
- Wire contract: `StandingRowRead.tiebreakers: list[TiebreakValue]` where `TiebreakValue = {label: str, value: float, format: "percent"}`.
- Never distribute or reference real, non-anonymized PII — the two TOM fixtures are already anonymized and committed; do not touch the anonymization.

---

### Task 1: Extract shared tiebreak helpers into `_shared.py`

**Files:**
- Create: `backend/app/tiebreak/_shared.py`
- Modify: `backend/app/tiebreak/owp_oomw.py`
- Test: `backend/tests/unit/test_owp_oomw_tiebreak.py` (existing — must pass unchanged, proving the extraction is behavior-preserving)

**Interfaces:**
- Produces: `points_and_rounds_played(rounds: Sequence[Round], win_points: int, tie_points: int, loss_points: int, bye_rounds_played: bool = True) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]`
- Produces: `opponents_faced(rounds: Sequence[Round]) -> dict[uuid.UUID, list[uuid.UUID]]`
- Produces: `average(values: dict[uuid.UUID, float], opponent_ids: list[uuid.UUID], floor: float) -> float`

- [ ] **Step 1: Run the existing OwpOomw test suite to capture the current-passing baseline**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_owp_oomw_tiebreak.py -v`
Expected: PASS (8 tests) — this is the regression baseline the extraction must not break.

- [ ] **Step 2: Create `backend/app/tiebreak/_shared.py`**

```python
import uuid
from collections.abc import Sequence

from app.models import MatchResult, Round


def points_and_rounds_played(
    rounds: Sequence[Round],
    win_points: int,
    tie_points: int,
    loss_points: int,
    bye_rounds_played: bool = True,
) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    """Tally match points and rounds-played per entry across `rounds`.

    `bye_rounds_played` controls whether a bye round counts toward the
    recipient's rounds-played denominator: `True` for MTG-style own-MWP
    (OwpOomwTiebreak), `False` for Pokémon's own win% (PokemonTiebreak,
    handbook §5.6.1 — a bye counts as a win but not a played round).
    """
    points: dict[uuid.UUID, int] = {}
    rounds_played: dict[uuid.UUID, int] = {}

    for round_ in rounds:
        for match in round_.matches:
            if match.entry2_id is None:
                points[match.entry1_id] = points.get(match.entry1_id, 0) + win_points
                if bye_rounds_played:
                    rounds_played[match.entry1_id] = rounds_played.get(match.entry1_id, 0) + 1
                continue

            rounds_played[match.entry1_id] = rounds_played.get(match.entry1_id, 0) + 1
            rounds_played[match.entry2_id] = rounds_played.get(match.entry2_id, 0) + 1

            if match.result is MatchResult.ENTRY1_WIN:
                points[match.entry1_id] = points.get(match.entry1_id, 0) + win_points
                points[match.entry2_id] = points.get(match.entry2_id, 0) + loss_points
            elif match.result is MatchResult.ENTRY2_WIN:
                points[match.entry2_id] = points.get(match.entry2_id, 0) + win_points
                points[match.entry1_id] = points.get(match.entry1_id, 0) + loss_points
            elif match.result is MatchResult.TIE:
                points[match.entry1_id] = points.get(match.entry1_id, 0) + tie_points
                points[match.entry2_id] = points.get(match.entry2_id, 0) + tie_points
            else:
                raise ValueError(f"round {round_.number} has an unreported match")

    return points, rounds_played


def opponents_faced(rounds: Sequence[Round]) -> dict[uuid.UUID, list[uuid.UUID]]:
    opponents: dict[uuid.UUID, list[uuid.UUID]] = {}

    for round_ in rounds:
        for match in round_.matches:
            if match.entry2_id is None:
                continue
            opponents.setdefault(match.entry1_id, []).append(match.entry2_id)
            opponents.setdefault(match.entry2_id, []).append(match.entry1_id)

    return opponents


def average(values: dict[uuid.UUID, float], opponent_ids: list[uuid.UUID], floor: float) -> float:
    if not opponent_ids:
        return floor
    return sum(values[opponent_id] for opponent_id in opponent_ids) / len(opponent_ids)
```

- [ ] **Step 3: Rewrite `backend/app/tiebreak/owp_oomw.py` to use the shared helpers**

```python
import uuid
from collections.abc import Sequence

from app.models import Entry, Round
from app.tiebreak._shared import average, opponents_faced, points_and_rounds_played
from app.tiebreak.base import TiebreakStrategy


class OwpOomwTiebreak(TiebreakStrategy):
    def __init__(
        self,
        floor: float = 0.33,
        win_points: int = 3,
        tie_points: int = 1,
        loss_points: int = 0,
    ):
        self.floor = floor
        self.win_points = win_points
        self.tie_points = tie_points
        self.loss_points = loss_points

    def compute(
        self, entries: Sequence[Entry], rounds: Sequence[Round]
    ) -> dict[uuid.UUID, tuple[float, float]]:
        points, rounds_played = points_and_rounds_played(
            rounds, self.win_points, self.tie_points, self.loss_points
        )
        opponents = opponents_faced(rounds)

        own_mwp = {
            entry.id: self._own_mwp(points.get(entry.id, 0), rounds_played.get(entry.id, 0))
            for entry in entries
        }
        omw_pct = {
            entry.id: average(own_mwp, opponents.get(entry.id, []), self.floor)
            for entry in entries
        }
        oomw_pct = {
            entry.id: average(omw_pct, opponents.get(entry.id, []), self.floor)
            for entry in entries
        }

        return {entry.id: (omw_pct[entry.id], oomw_pct[entry.id]) for entry in entries}

    def _own_mwp(self, points: int, rounds_played: int) -> float:
        if rounds_played == 0:
            return 0.0
        return max(points / (self.win_points * rounds_played), self.floor)

    def labels(self) -> tuple[str, str]:
        return ("OMW%", "OOMW%")
```

Note: `labels()` is added here because `TiebreakStrategy` will become abstract for it in Task 2 — added now so this file is self-consistent at every commit.

- [ ] **Step 4: Run the OwpOomw test suite again to confirm the extraction is behavior-preserving**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_owp_oomw_tiebreak.py -v`
Expected: PASS (8 tests) — identical result to Step 1.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tiebreak/_shared.py backend/app/tiebreak/owp_oomw.py
git commit -m "refactor(tiebreak): extract shared point/opponent helpers into _shared.py"
```

---

### Task 2: Add `labels()` and `break_tie()` to `TiebreakStrategy`

**Files:**
- Modify: `backend/app/tiebreak/base.py`
- Test: `backend/tests/unit/test_tiebreak_base.py` (new)

**Interfaces:**
- Consumes: nothing new
- Produces: `TiebreakStrategy.labels() -> tuple[str, ...]` (abstract), `TiebreakStrategy.break_tie(entry_a_id: uuid.UUID, entry_b_id: uuid.UUID, rounds: Sequence[Round]) -> int | None` (concrete, default returns `None`)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_tiebreak_base.py
import uuid

import pytest

from app.tiebreak.base import TiebreakStrategy


class _MinimalStrategy(TiebreakStrategy):
    def compute(self, entries, rounds):
        return {}

    def labels(self):
        return ("Stat A", "Stat B")


def test_tiebreak_strategy_is_abstract():
    with pytest.raises(TypeError):
        TiebreakStrategy()


def test_labels_is_required_by_subclasses():
    class _NoLabels(TiebreakStrategy):
        def compute(self, entries, rounds):
            return {}

    with pytest.raises(TypeError):
        _NoLabels()


def test_break_tie_defaults_to_none():
    strategy = _MinimalStrategy()

    result = strategy.break_tie(uuid.uuid4(), uuid.uuid4(), rounds=[])

    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_tiebreak_base.py -v`
Expected: FAIL — `labels` isn't a required abstract method yet, so `test_labels_is_required_by_subclasses` fails (no `TypeError` raised).

- [ ] **Step 3: Update `backend/app/tiebreak/base.py`**

```python
import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.models import Entry, Round


class TiebreakStrategy(ABC):
    @abstractmethod
    def compute(
        self, entries: Sequence[Entry], rounds: Sequence[Round]
    ) -> dict[uuid.UUID, tuple[float, ...]]:
        """Per-entry ordered tiebreak chain, most-significant value first.

        Receives ALL entries and the full round history (not just one
        entry's own matches) so a strategy can read any player's own
        round-by-round result sequence, not only opponents' final records.
        """

    @abstractmethod
    def labels(self) -> tuple[str, ...]:
        """Column labels matching compute()'s tuple order, most-significant first."""

    def break_tie(
        self, entry_a_id: uuid.UUID, entry_b_id: uuid.UUID, rounds: Sequence[Round]
    ) -> int | None:
        """Pairwise fallback for two entries tied after compute()'s chain.

        Returns -1 if entry_a_id ranks higher, 1 if entry_b_id ranks
        higher, or None if this strategy has no pairwise fallback (the
        default) or the fallback can't resolve this particular pair.
        """
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_tiebreak_base.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full backend unit suite to confirm nothing else broke**

Run: `cd backend && .venv/bin/python -m pytest tests/unit -v`
Expected: PASS — `OwpOomwTiebreak` already has `labels()` from Task 1, so it remains instantiable.

- [ ] **Step 6: Commit**

```bash
git add backend/app/tiebreak/base.py backend/tests/unit/test_tiebreak_base.py
git commit -m "feat(tiebreak): add labels() and break_tie() to TiebreakStrategy"
```

---

### Task 3: `PokemonTiebreak` — Op Win% / Op Op Win% compute()

**Files:**
- Create: `backend/app/tiebreak/pokemon.py`
- Test: `backend/tests/unit/test_pokemon_tiebreak.py`

**Interfaces:**
- Consumes: `points_and_rounds_played`, `opponents_faced`, `average` from `app.tiebreak._shared` (Task 1); `TiebreakStrategy` from `app.tiebreak.base` (Task 2)
- Produces: `PokemonTiebreak(win_points=3, tie_points=1, loss_points=0)`, `.compute(entries, rounds) -> dict[uuid.UUID, tuple[float, float]]`, `.labels() -> ("Op Win%", "Op Op Win%")`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_pokemon_tiebreak.py
import uuid

import pytest

from app.models import Entry, Match, MatchResult, Round
from app.tiebreak.pokemon import PokemonTiebreak


def _entry(dropped_at_round: int | None = None) -> Entry:
    return Entry(
        id=uuid.uuid4(),
        pod_id=uuid.uuid4(),
        player_uuid=uuid.uuid4(),
        source_system="test",
        metadata_={},
        dropped_at_round=dropped_at_round,
    )


def _round(number: int, matches: list[Match]) -> Round:
    round_ = Round(id=uuid.uuid4(), pod_id=uuid.uuid4(), number=number)
    round_.matches = matches
    return round_


def _match(entry1: Entry, entry2: Entry | None, result: MatchResult | None = None) -> Match:
    return Match(
        id=uuid.uuid4(),
        round_id=uuid.uuid4(),
        entry1_id=entry1.id,
        entry2_id=entry2.id if entry2 else None,
        result=result if result is not None else MatchResult.UNREPORTED,
    )


def test_labels_are_pokemon_specific():
    assert PokemonTiebreak().labels() == ("Op Win%", "Op Op Win%")


def test_floor_engages_for_a_winless_opponent():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY1_WIN)])

    tiebreaks = PokemonTiebreak().compute([a, b], [round1])

    # b: 0 wins / 1 round played -> raw 0.0, floored to 0.25. a's only
    # opponent is b, so Op Win%(a) is exactly that floored value.
    assert tiebreaks[a.id][0] == pytest.approx(0.25)


def test_completed_entry_caps_at_100_percent():
    a, b, c = _entry(), _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY1_WIN)])
    round2 = _round(2, [_match(a, c, MatchResult.ENTRY1_WIN)])

    tiebreaks = PokemonTiebreak().compute([a, b, c], [round1, round2])

    # a went 2-0 in 2 rounds, did not drop -> raw 1.0, capped at 1.0
    # (completed cap), not lowered. b's only opponent is a, so
    # Op Win%(b) reads a's own win% directly.
    assert tiebreaks[b.id][0] == pytest.approx(1.0)


def test_dropped_entry_caps_at_75_percent_even_at_a_perfect_record():
    a, b, c = _entry(dropped_at_round=2), _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY1_WIN)])
    round2 = _round(2, [_match(a, c, MatchResult.ENTRY1_WIN)])

    tiebreaks = PokemonTiebreak().compute([a, b, c], [round1, round2])

    # a went 2-0 (raw 1.0) but dropped after round 2 -> capped at 0.75,
    # not 1.0. b's only opponent is a, so Op Win%(b) reads the capped value.
    assert tiebreaks[b.id][0] == pytest.approx(0.75)


def test_bye_round_excluded_from_denominator_but_counts_as_a_win():
    a, b, c = _entry(), _entry(), _entry()
    round1 = _round(1, [_match(a, None), _match(b, c, MatchResult.ENTRY1_WIN)])
    round2 = _round(2, [_match(a, b, MatchResult.ENTRY1_WIN)])

    tiebreaks = PokemonTiebreak().compute([a, b, c], [round1, round2])

    # a's own record: bye (win, round excluded from denominator) + round2
    # win vs b = 2 wins / 1 round played (only round2 counts) = 1.0, capped
    # at 1.0. a's only *opponent* across both rounds is b (round2) -- the
    # bye round never adds a phantom opponent (matches OwpOomw's rule).
    # b's own win%: 0 wins (round1 win vs c, round2 loss vs a) = 1 win / 2
    # rounds played = 0.5.
    b_own_win_pct = 0.5
    assert tiebreaks[a.id][0] == pytest.approx(b_own_win_pct)


def test_op_op_win_pct_averages_opponents_op_win_pct():
    a, b, c, d = _entry(), _entry(), _entry(), _entry()
    round1 = _round(
        1,
        [
            _match(a, b, MatchResult.ENTRY1_WIN),
            _match(c, d, MatchResult.ENTRY1_WIN),
        ],
    )
    round2 = _round(2, [_match(a, c, MatchResult.ENTRY2_WIN)])  # c beats a

    tiebreaks = PokemonTiebreak().compute([a, b, c, d], [round1, round2])

    # a's opponents are b and c -> Op Op Win%(a) averages Op Win%(b) and
    # Op Win%(c). b's only opponent is a (own win% = 1 pt / 2 rounds =
    # 0.5) -> Op Win%(b) = 0.5. c's opponents are d and a: own_win_pct(d)
    # = 0/1 rounds -> floored 0.25; own_win_pct(a) = 3/(3*2) = 0.5 (a went
    # 1-1). Op Win%(c) = (0.25 + 0.5) / 2 = 0.375.
    op_win_pct_b = 0.5
    op_win_pct_c = 0.375
    assert tiebreaks[a.id][1] == pytest.approx((op_win_pct_b + op_win_pct_c) / 2)


def test_tie_contributes_partial_credit_via_match_points_not_a_binary_win():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.TIE)])

    tiebreaks = PokemonTiebreak(win_points=3, tie_points=1, loss_points=0).compute([a, b], [round1])

    # b's own win%: 1 tie point / (3 * 1 round) = 0.333, above the 0.25
    # floor -- a tie contributes fractional credit via match points, the
    # same mechanism OwpOomwTiebreak already uses (resolves the research
    # doc's tie-numerator open item without new formula logic).
    assert tiebreaks[a.id][0] == pytest.approx(1 / 3)


def test_entry_with_only_a_bye_gets_floor_not_zero_rounds_played_crash():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, None)])

    tiebreaks = PokemonTiebreak().compute([a, b], [round1])

    assert tiebreaks[a.id][0] == pytest.approx(0.25)
    assert tiebreaks[a.id][1] == pytest.approx(0.25)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_pokemon_tiebreak.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tiebreak.pokemon'`

- [ ] **Step 3: Create `backend/app/tiebreak/pokemon.py`**

```python
import uuid
from collections.abc import Sequence

from app.models import Entry, MatchResult, Round
from app.tiebreak._shared import average, opponents_faced, points_and_rounds_played
from app.tiebreak.base import TiebreakStrategy

FLOOR = 0.25
COMPLETED_CAP = 1.0
DROPPED_CAP = 0.75


class PokemonTiebreak(TiebreakStrategy):
    """Op Win% / Op Op Win% chain per Play! Pokémon Tournament Rules
    Handbook §5.3.3, §5.3.3.1, §5.5.1.1 — see docs/pokemon-tiebreak-research.md."""

    def __init__(self, win_points: int = 3, tie_points: int = 1, loss_points: int = 0):
        self.win_points = win_points
        self.tie_points = tie_points
        self.loss_points = loss_points

    def compute(
        self, entries: Sequence[Entry], rounds: Sequence[Round]
    ) -> dict[uuid.UUID, tuple[float, float]]:
        points, rounds_played = points_and_rounds_played(
            rounds,
            self.win_points,
            self.tie_points,
            self.loss_points,
            bye_rounds_played=False,
        )
        opponents = opponents_faced(rounds)
        dropped = {entry.id: entry.dropped_at_round is not None for entry in entries}

        own_win_pct = {
            entry.id: self._own_win_pct(
                points.get(entry.id, 0), rounds_played.get(entry.id, 0), dropped[entry.id]
            )
            for entry in entries
        }
        op_win_pct = {
            entry.id: average(own_win_pct, opponents.get(entry.id, []), FLOOR)
            for entry in entries
        }
        op_op_win_pct = {
            entry.id: average(op_win_pct, opponents.get(entry.id, []), FLOOR)
            for entry in entries
        }

        return {entry.id: (op_win_pct[entry.id], op_op_win_pct[entry.id]) for entry in entries}

    def _own_win_pct(self, points: int, rounds_played: int, dropped: bool) -> float:
        if rounds_played == 0:
            return FLOOR
        cap = DROPPED_CAP if dropped else COMPLETED_CAP
        raw = points / (self.win_points * rounds_played)
        return max(FLOOR, min(cap, raw))

    def labels(self) -> tuple[str, str]:
        return ("Op Win%", "Op Op Win%")

    def break_tie(
        self, entry_a_id: uuid.UUID, entry_b_id: uuid.UUID, rounds: Sequence[Round]
    ) -> int | None:
        return None  # implemented in Task 4
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_pokemon_tiebreak.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/tiebreak/pokemon.py backend/tests/unit/test_pokemon_tiebreak.py
git commit -m "feat(tiebreak): add PokemonTiebreak Op Win%/Op Op Win% compute (FR28)"
```

---

### Task 4: `PokemonTiebreak.break_tie()` — head-to-head fallback

**Files:**
- Modify: `backend/app/tiebreak/pokemon.py`
- Test: `backend/tests/unit/test_pokemon_tiebreak.py`

**Interfaces:**
- Produces: `PokemonTiebreak.break_tie(entry_a_id, entry_b_id, rounds) -> int | None` per the Global Constraints convention (`-1`/`1`/`None`)

- [ ] **Step 1: Write the failing tests (append to `test_pokemon_tiebreak.py`)**

```python
def test_break_tie_returns_negative_one_when_entry_a_won():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY1_WIN)])

    result = PokemonTiebreak().break_tie(a.id, b.id, [round1])

    assert result == -1


def test_break_tie_returns_positive_one_when_entry_b_won():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY2_WIN)])

    result = PokemonTiebreak().break_tie(a.id, b.id, [round1])

    assert result == 1


def test_break_tie_is_order_independent():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY1_WIN)])

    assert PokemonTiebreak().break_tie(a.id, b.id, [round1]) == -1
    assert PokemonTiebreak().break_tie(b.id, a.id, [round1]) == 1


def test_break_tie_returns_none_when_the_shared_match_was_a_tie():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.TIE)])

    result = PokemonTiebreak().break_tie(a.id, b.id, [round1])

    assert result is None


def test_break_tie_returns_none_when_they_never_played():
    a, b, c = _entry(), _entry(), _entry()
    round1 = _round(1, [_match(a, c, MatchResult.ENTRY1_WIN)])

    result = PokemonTiebreak().break_tie(a.id, b.id, [round1])

    assert result is None


def test_break_tie_ignores_a_bye_match_between_unrelated_entries():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, None)])

    result = PokemonTiebreak().break_tie(a.id, b.id, [round1])

    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_pokemon_tiebreak.py -v -k break_tie`
Expected: FAIL — current `break_tie` always returns `None`, so the win/loss-detecting assertions fail.

- [ ] **Step 3: Implement `break_tie()` in `backend/app/tiebreak/pokemon.py`**

Replace the Task 3 placeholder body:

```python
    def break_tie(
        self, entry_a_id: uuid.UUID, entry_b_id: uuid.UUID, rounds: Sequence[Round]
    ) -> int | None:
        for round_ in rounds:
            for match in round_.matches:
                if match.entry2_id is None:
                    continue
                if {match.entry1_id, match.entry2_id} != {entry_a_id, entry_b_id}:
                    continue
                if match.result is MatchResult.ENTRY1_WIN:
                    winner_id = match.entry1_id
                elif match.result is MatchResult.ENTRY2_WIN:
                    winner_id = match.entry2_id
                else:
                    return None
                return -1 if winner_id == entry_a_id else 1
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_pokemon_tiebreak.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/tiebreak/pokemon.py backend/tests/unit/test_pokemon_tiebreak.py
git commit -m "feat(tiebreak): add PokemonTiebreak.break_tie head-to-head fallback (FR29)"
```

---

### Task 5: `GameModule.tiebreak_strategy()`

**Files:**
- Modify: `backend/app/games/base.py`
- Modify: `backend/app/games/generic.py`
- Modify: `backend/app/games/pokemon.py`
- Test: `backend/tests/unit/test_games.py`

**Interfaces:**
- Consumes: `OwpOomwTiebreak` (Task 1), `PokemonTiebreak` (Task 3/4)
- Produces: `GameModule.tiebreak_strategy() -> TiebreakStrategy` (abstract); `GenericGameModule.tiebreak_strategy()` returns `OwpOomwTiebreak(win_points=3, tie_points=1, loss_points=0)`; `PokemonGameModule.tiebreak_strategy()` returns `PokemonTiebreak(win_points=WIN_POINTS, tie_points=TIE_POINTS, loss_points=LOSS_POINTS)`

- [ ] **Step 1: Write the failing tests (append to `test_games.py`)**

```python
from app.tiebreak.owp_oomw import OwpOomwTiebreak
from app.tiebreak.pokemon import PokemonTiebreak


def test_generic_game_module_tiebreak_strategy_is_owp_oomw():
    strategy = GenericGameModule().tiebreak_strategy()

    assert isinstance(strategy, OwpOomwTiebreak)
    assert strategy.labels() == ("OMW%", "OOMW%")


def test_pokemon_game_module_tiebreak_strategy_is_pokemon_tiebreak():
    strategy = PokemonGameModule().tiebreak_strategy()

    assert isinstance(strategy, PokemonTiebreak)
    assert strategy.labels() == ("Op Win%", "Op Op Win%")
    assert strategy.win_points == PokemonGameModule.WIN_POINTS
    assert strategy.tie_points == PokemonGameModule.TIE_POINTS
    assert strategy.loss_points == PokemonGameModule.LOSS_POINTS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_games.py -v -k tiebreak_strategy`
Expected: FAIL — `AttributeError: 'GenericGameModule' object has no attribute 'tiebreak_strategy'`

- [ ] **Step 3: Update `backend/app/games/base.py`**

```python
from abc import ABC, abstractmethod

from app.tiebreak.base import TiebreakStrategy


class GameModule(ABC):
    slug: str

    @abstractmethod
    def validate_entry_metadata(self, metadata: dict) -> None:
        """Raise ValueError if metadata is invalid for this game."""

    @abstractmethod
    def tiebreak_strategy(self) -> TiebreakStrategy:
        """Return this game's TiebreakStrategy for Swiss standings/ranking."""
```

- [ ] **Step 4: Update `backend/app/games/generic.py`**

```python
from app.games.base import GameModule
from app.tiebreak.base import TiebreakStrategy
from app.tiebreak.owp_oomw import OwpOomwTiebreak


class GenericGameModule(GameModule):
    slug = "generic"

    WIN_POINTS = 3
    TIE_POINTS = 1
    LOSS_POINTS = 0

    def validate_entry_metadata(self, metadata: dict) -> None:
        return None

    def tiebreak_strategy(self) -> TiebreakStrategy:
        return OwpOomwTiebreak(
            win_points=self.WIN_POINTS, tie_points=self.TIE_POINTS, loss_points=self.LOSS_POINTS
        )
```

- [ ] **Step 5: Update `backend/app/games/pokemon.py`**

Add the import and method (keep the existing `validate_entry_metadata` body unchanged), and drop the now-resolved "not wired in yet" hedge from the class docstring:

```python
from urllib.parse import urlsplit

from app.games.base import GameModule
from app.tiebreak.base import TiebreakStrategy
from app.tiebreak.pokemon import PokemonTiebreak

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
    S5.5.6. Match points below match handbook S5.3.2 and drive
    PokemonTiebreak's Op Win%/Op Op Win% chain (Phase 18, FR28/FR29).
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

        if decklist_url != decklist_url.strip() or any(c.isspace() for c in decklist_url):
            raise ValueError(_DECKLIST_URL_ERROR)

        try:
            parts = urlsplit(decklist_url)
        except ValueError:
            raise ValueError(_DECKLIST_URL_ERROR) from None

        if parts.scheme != "https":
            raise ValueError(_DECKLIST_URL_ERROR)

        path_prefix = _ALLOWED_DECKLIST_HOSTS.get(parts.hostname or "")
        if path_prefix is None or not parts.path.startswith(path_prefix):
            raise ValueError(_DECKLIST_URL_ERROR)

        id_portion = parts.path[len(path_prefix) :]
        if not id_portion:
            raise ValueError(_DECKLIST_URL_ERROR)

        if "/" in id_portion:
            raise ValueError(_DECKLIST_URL_ERROR)

        if parts.query or parts.fragment:
            raise ValueError(_DECKLIST_URL_ERROR)

    def tiebreak_strategy(self) -> TiebreakStrategy:
        return PokemonTiebreak(
            win_points=self.WIN_POINTS, tie_points=self.TIE_POINTS, loss_points=self.LOSS_POINTS
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_games.py -v`
Expected: PASS (all tests, including the 2 new ones)

- [ ] **Step 7: Commit**

```bash
git add backend/app/games/base.py backend/app/games/generic.py backend/app/games/pokemon.py backend/tests/unit/test_games.py
git commit -m "feat(games): add GameModule.tiebreak_strategy(), wire Pokemon to PokemonTiebreak"
```

---

### Task 6: `app/ruleset.py` — `Ruleset` + `get_ruleset_or_422`

**Files:**
- Create: `backend/app/ruleset.py`
- Test: `backend/tests/unit/test_ruleset.py`

**Interfaces:**
- Consumes: `SwissFormat` (`app.formats.swiss`), `get_game_module` (`app.games.registry`, Task 5's `tiebreak_strategy()`)
- Produces: `Ruleset` frozen dataclass (`format: TournamentFormat`, `game_module: GameModule`); `get_ruleset_or_422(pod: Pod) -> Ruleset`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_ruleset.py
import uuid

import pytest
from fastapi import HTTPException

from app.formats.swiss import SwissFormat
from app.games.pokemon import PokemonGameModule
from app.models import Pod
from app.ruleset import Ruleset, get_ruleset_or_422
from app.tiebreak.owp_oomw import OwpOomwTiebreak
from app.tiebreak.pokemon import PokemonTiebreak


def _pod(format_slug: str, game_slug: str) -> Pod:
    return Pod(id=uuid.uuid4(), event_id=uuid.uuid4(), format_slug=format_slug, game_slug=game_slug)


def test_resolves_swiss_generic_to_owp_oomw():
    ruleset = get_ruleset_or_422(_pod("swiss", "generic"))

    assert isinstance(ruleset, Ruleset)
    assert isinstance(ruleset.format, SwissFormat)
    assert isinstance(ruleset.format.tiebreak, OwpOomwTiebreak)


def test_resolves_swiss_pokemon_to_pokemon_tiebreak():
    ruleset = get_ruleset_or_422(_pod("swiss", "pokemon-tcg"))

    assert isinstance(ruleset.format, SwissFormat)
    assert isinstance(ruleset.format.tiebreak, PokemonTiebreak)
    assert isinstance(ruleset.game_module, PokemonGameModule)


def test_unrecognized_game_slug_raises_422():
    with pytest.raises(HTTPException) as exc_info:
        get_ruleset_or_422(_pod("swiss", "not-a-real-game"))

    assert exc_info.value.status_code == 422


def test_unrecognized_format_slug_raises_422():
    with pytest.raises(HTTPException) as exc_info:
        get_ruleset_or_422(_pod("not-a-real-format", "generic"))

    assert exc_info.value.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_ruleset.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ruleset'`

- [ ] **Step 3: Create `backend/app/ruleset.py`**

```python
from dataclasses import dataclass

from fastapi import HTTPException

from app.formats.base import TournamentFormat
from app.formats.swiss import SwissFormat
from app.games.base import GameModule
from app.games.registry import get_game_module
from app.models import Pod


@dataclass(frozen=True)
class Ruleset:
    format: TournamentFormat
    game_module: GameModule


def get_ruleset_or_422(pod: Pod) -> Ruleset:
    """Resolve pod's (format_slug, game_slug) into a Ruleset, or raise HTTPException(422)."""
    if pod.format_slug != "swiss":
        raise HTTPException(
            status_code=422,
            detail=f"pod's format_slug {pod.format_slug!r} is not a recognized tournament format",
        )

    try:
        game_module = get_game_module(pod.game_slug)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"pod's game_slug {pod.game_slug!r} is not a recognized game module",
        ) from exc

    tournament_format = SwissFormat(tiebreak=game_module.tiebreak_strategy())
    return Ruleset(format=tournament_format, game_module=game_module)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_ruleset.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/ruleset.py backend/tests/unit/test_ruleset.py
git commit -m "feat(ruleset): add Ruleset factory resolving (format_slug, game_slug) to a tiebreak-aware SwissFormat"
```

---

### Task 7: `_rank_entries` pairwise grouping pass (FR29 wiring into Swiss)

**Files:**
- Modify: `backend/app/formats/swiss.py`
- Test: `backend/tests/unit/test_swiss_format.py`

**Interfaces:**
- Consumes: `TiebreakStrategy.break_tie()` (Task 2/4)
- Produces: `_rank_entries(entries, standings, tiebreaks, tiebreak: TiebreakStrategy, rounds: Sequence[Round]) -> list[Entry]` (signature change — 2 new required params)

- [ ] **Step 1: Update the existing `_rank_entries` test for the new signature**

In `backend/tests/unit/test_swiss_format.py`, replace `test_rank_entries_orders_by_points_then_tiebreak_then_uuid`'s call:

```python
def test_rank_entries_orders_by_points_then_tiebreak_then_uuid():
    from app.formats.swiss import _rank_entries
    from app.tiebreak.owp_oomw import OwpOomwTiebreak

    e_low_points, e_high_tiebreak, e_low_tiebreak, e_tied_a, e_tied_b = (
        _entry(),
        _entry(),
        _entry(),
        _entry(),
        _entry(),
    )
    standings = {
        e_low_points.id: 0,
        e_high_tiebreak.id: 3,
        e_low_tiebreak.id: 3,
        e_tied_a.id: 6,
        e_tied_b.id: 6,
    }
    tiebreaks = {
        e_low_points.id: (0.9, 0.9),
        e_high_tiebreak.id: (0.7, 0.7),
        e_low_tiebreak.id: (0.4, 0.4),
        e_tied_a.id: (0.5, 0.5),
        e_tied_b.id: (0.5, 0.5),
    }

    ranked = _rank_entries(
        [e_low_points, e_high_tiebreak, e_low_tiebreak, e_tied_a, e_tied_b],
        standings,
        tiebreaks,
        OwpOomwTiebreak(),
        rounds=[],
    )

    # e_tied_a/e_tied_b (6 pts) rank above e_high_tiebreak/e_low_tiebreak
    # (3 pts) despite a lower tiebreak value -- points always wins first.
    assert {r.id for r in ranked[:2]} == {e_tied_a.id, e_tied_b.id}
    # Within the 3-point group, the higher tiebreak value ranks first.
    assert ranked[2].id == e_high_tiebreak.id
    assert ranked[3].id == e_low_tiebreak.id
    # e_low_points is last regardless of its (unused) high tiebreak value.
    assert ranked[4].id == e_low_points.id
    # e_tied_a/e_tied_b are tied on both points AND tiebreak -- OwpOomwTiebreak
    # has no break_tie(), so UUID string order is the last-resort fallback.
    assert [r.id for r in ranked[:2]] == sorted([e_tied_a.id, e_tied_b.id], key=str)
```

Add new tests (append):

```python
def test_rank_entries_uses_break_tie_for_exactly_two_tied_entries():
    from app.formats.swiss import _rank_entries

    e_winner, e_loser = _entry(), _entry()
    standings = {e_winner.id: 3, e_loser.id: 3}
    tiebreaks = {e_winner.id: (0.5, 0.5), e_loser.id: (0.5, 0.5)}
    match = Match(
        id=uuid.uuid4(),
        round_id=uuid.uuid4(),
        entry1_id=e_loser.id,
        entry2_id=e_winner.id,
        result=MatchResult.ENTRY2_WIN,
    )
    round1 = _round(1, [match])

    class _StubTiebreak:
        def break_tie(self, entry_a_id, entry_b_id, rounds):
            # entry_a_id/entry_b_id arrive in _rank_entries' internal
            # group order; assert head-to-head result regardless of order.
            if entry_a_id == e_winner.id:
                return -1
            return 1

    ranked = _rank_entries(
        [e_winner, e_loser], standings, tiebreaks, _StubTiebreak(), rounds=[round1]
    )

    assert ranked[0].id == e_winner.id
    assert ranked[1].id == e_loser.id


def test_rank_entries_falls_back_to_uuid_order_when_break_tie_returns_none():
    from app.formats.swiss import _rank_entries

    e_a, e_b = _entry(), _entry()
    standings = {e_a.id: 3, e_b.id: 3}
    tiebreaks = {e_a.id: (0.5, 0.5), e_b.id: (0.5, 0.5)}

    class _StubTiebreak:
        def break_tie(self, entry_a_id, entry_b_id, rounds):
            return None

    ranked = _rank_entries([e_a, e_b], standings, tiebreaks, _StubTiebreak(), rounds=[])

    assert [r.id for r in ranked] == sorted([e_a.id, e_b.id], key=str)


def test_rank_entries_never_calls_break_tie_for_a_three_way_tie():
    from app.formats.swiss import _rank_entries

    e_a, e_b, e_c = _entry(), _entry(), _entry()
    standings = {e_a.id: 3, e_b.id: 3, e_c.id: 3}
    tiebreaks = {e_a.id: (0.5, 0.5), e_b.id: (0.5, 0.5), e_c.id: (0.5, 0.5)}

    class _ExplodingTiebreak:
        def break_tie(self, entry_a_id, entry_b_id, rounds):
            raise AssertionError("break_tie must not be called for a 3+ way tie")

    ranked = _rank_entries(
        [e_a, e_b, e_c], standings, tiebreaks, _ExplodingTiebreak(), rounds=[]
    )

    assert [r.id for r in ranked] == sorted([e_a.id, e_b.id, e_c.id], key=str)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_swiss_format.py -v -k rank_entries`
Expected: FAIL — `TypeError: _rank_entries() missing 2 required positional arguments`

- [ ] **Step 3: Update `_rank_entries` and its two call sites in `backend/app/formats/swiss.py`**

Add `import itertools` at the top and the `TiebreakStrategy` import:

```python
import itertools
from collections.abc import Sequence

from app.formats.base import Pairing, StandingRow, TournamentFormat
from app.models import Entry, MatchResult, Round
from app.tiebreak.base import TiebreakStrategy
from app.tiebreak.owp_oomw import OwpOomwTiebreak
```

Replace `_rank_entries`:

```python
def _rank_entries(
    entries: Sequence[Entry],
    standings: dict,
    tiebreaks: dict,
    tiebreak: TiebreakStrategy,
    rounds: Sequence[Round],
) -> list:
    sorted_entries = sorted(
        entries,
        key=lambda entry: (
            -standings.get(entry.id, 0),
            tuple(-v for v in tiebreaks.get(entry.id, ())),
            str(entry.id),
        ),
    )

    ranked: list = []
    for _, group_iter in itertools.groupby(
        sorted_entries,
        key=lambda entry: (standings.get(entry.id, 0), tiebreaks.get(entry.id, ())),
    ):
        group = list(group_iter)
        if len(group) == 2:
            entry_a, entry_b = group
            result = tiebreak.break_tie(entry_a.id, entry_b.id, rounds)
            if result == 1:
                group = [entry_b, entry_a]
        ranked.extend(group)

    return ranked
```

Update the two call sites — in `generate_round`:

```python
        ranked = _rank_entries(active_entries, standings, tiebreaks, self.tiebreak, previous_rounds)
```

and in `compute_standings`:

```python
        ranked = _rank_entries(entries, standings, tiebreaks, self.tiebreak, rounds)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_swiss_format.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Run the full backend unit + integration suite**

Run: `cd backend && .venv/bin/python -m pytest tests -v`
Expected: PASS — this is the last change before the wire-contract task, so this confirms `SwissFormat`'s round-generation and standings paths still work end to end with the new `_rank_entries` signature.

- [ ] **Step 6: Commit**

```bash
git add backend/app/formats/swiss.py backend/tests/unit/test_swiss_format.py
git commit -m "feat(swiss): wire break_tie() into _rank_entries for exactly-two-way ties (FR29)"
```

---

### Task 8: Wire contract — labeled `TiebreakValue` (#57) + `Ruleset` at the round-generation/report call sites

**Files:**
- Modify: `backend/app/schemas/report.py`
- Modify: `backend/app/routers/pods.py`
- Modify: `backend/app/routers/rounds.py`
- Test: `backend/tests/integration/test_report_flow_api.py`

**Interfaces:**
- Consumes: `get_ruleset_or_422` (Task 6), `strategy.labels()` (Task 2)
- Produces: `TiebreakValue` Pydantic model (`label: str`, `value: float`, `format: Literal["percent"]`); `StandingRowRead.tiebreakers: list[TiebreakValue]`

- [ ] **Step 1: Update the existing integration test for the new wire shape**

In `backend/tests/integration/test_report_flow_api.py`, update the two assertions in `test_report_ranks_by_omw_when_match_points_tie`:

```python
    assert standings[w1]["points"] == standings[l1]["points"] == 3
    assert len(standings[w1]["tiebreakers"]) == 2
    assert standings[w1]["tiebreakers"][0] == {"label": "OMW%", "value": pytest.approx(0.75), "format": "percent"}
    assert standings[l1]["tiebreakers"][0] == {"label": "OMW%", "value": pytest.approx(0.415), "format": "percent"}
    assert standings[w1]["rank"] < standings[l1]["rank"]
```

`pytest.approx` doesn't compare inside a dict via `==` against a plain float the same way — use explicit field access instead:

```python
    assert standings[w1]["points"] == standings[l1]["points"] == 3
    assert len(standings[w1]["tiebreakers"]) == 2
    assert standings[w1]["tiebreakers"][0]["label"] == "OMW%"
    assert standings[w1]["tiebreakers"][0]["value"] == pytest.approx(0.75)
    assert standings[w1]["tiebreakers"][0]["format"] == "percent"
    assert standings[l1]["tiebreakers"][0]["value"] == pytest.approx(0.415)
    assert standings[w1]["rank"] < standings[l1]["rank"]
```

Add a new test (append to the same file):

```python
def test_report_labels_tiebreakers_per_game_module(api_client, make_token):
    """A pokemon-tcg pod's report uses PokemonTiebreak's labels; a generic
    pod's report uses OwpOomwTiebreak's labels -- proves get_ruleset_or_422
    resolves the game-specific strategy at the report call site (#57)."""
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = api_client.post(
        "/organizations", json={"name": "Test Org"}, headers=_auth_headers(token)
    ).json()["id"]
    event_id = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Test Event", "organization_id": org_id},
        headers=_auth_headers(token),
    ).json()["id"]
    pod_id = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "pokemon-tcg"},
        headers=_auth_headers(token),
    ).json()["id"]
    for _ in range(2):
        _add_entry(api_client, token, pod_id)
    api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    report = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token)).json()

    labels = [tb["label"] for tb in report["standings"][0]["tiebreakers"]]
    assert labels == ["Op Win%", "Op Op Win%"]
    assert all(tb["format"] == "percent" for tb in report["standings"][0]["tiebreakers"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_report_flow_api.py -v`
Expected: FAIL — current `StandingRowRead.tiebreakers` is `list[float]`, so `tiebreakers[0]["label"]` raises `TypeError: 'float' object is not subscriptable`.

- [ ] **Step 3: Update `backend/app/schemas/report.py`**

```python
import uuid
from typing import Literal

from pydantic import BaseModel


class TiebreakValue(BaseModel):
    label: str
    value: float
    format: Literal["percent"]


class StandingRowRead(BaseModel):
    entry_id: uuid.UUID
    points: int
    rank: int
    tiebreakers: list[TiebreakValue]


class PodReport(BaseModel):
    is_complete: bool
    rounds_played: int
    is_partial: bool
    active_entry_count: int
    recommended_rounds: int
    standings: list[StandingRowRead]
```

- [ ] **Step 4: Update `backend/app/routers/pods.py`**

Replace the `get_tournament_format_or_422` import and its one usage with `get_ruleset_or_422`, and build labeled `TiebreakValue`s in `get_pod_report`:

```python
from app.ruleset import get_ruleset_or_422
```

(remove `from app.formats.registry import get_tournament_format_or_422`)

```python
from app.schemas.report import PodReport, StandingRowRead, TiebreakValue
```

In `get_pod_report`:

```python
    ruleset = get_ruleset_or_422(pod)
    tournament_format = ruleset.format

    all_entries = db.query(Entry).filter_by(pod_id=pod_id).order_by(Entry.id).all()
    all_rounds = db.query(Round).filter_by(pod_id=pod_id).order_by(Round.number).all()

    usable_rounds = all_rounds
    is_partial = False
    if usable_rounds and not _round_fully_reported(usable_rounds[-1]):
        usable_rounds = usable_rounds[:-1]
        is_partial = True

    try:
        standings = tournament_format.compute_standings(all_entries, usable_rounds)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    active_entry_count = sum(1 for entry in all_entries if entry.dropped_at_round is None)
    labels = tournament_format.tiebreak.labels()

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
                tiebreakers=[
                    TiebreakValue(label=label, value=value, format="percent")
                    for label, value in zip(labels, row.tiebreakers, strict=True)
                ],
            )
            for row in standings
        ],
    )
```

`create_pod`/`update_pod`'s `_validate_game_slug` helper and `get_game_module` import stay as-is — they only validate the slug, no tiebreak strategy needed there.

- [ ] **Step 5: Update `backend/app/routers/rounds.py`**

Replace the import and the one usage:

```python
from app.ruleset import get_ruleset_or_422
```

(remove `from app.formats.registry import get_tournament_format_or_422`)

```python
    tournament_format = get_ruleset_or_422(pod).format
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/integration/test_report_flow_api.py -v`
Expected: PASS (3 tests, including the new one)

- [ ] **Step 7: Run the full backend suite**

Run: `cd backend && .venv/bin/python -m pytest tests -v`
Expected: PASS — confirms `formats/registry.py`'s `FORMATS` singleton is now unused at these two call sites but still compiles (it's untouched, per the design's "bypass, don't remove" note) and nothing else references the old `tiebreakers[0]` float shape.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/report.py backend/app/routers/pods.py backend/app/routers/rounds.py backend/tests/integration/test_report_flow_api.py
git commit -m "feat(api): label tiebreaker wire contract with strategy.labels() (#57), route report/round-generation through Ruleset"
```

---

### Task 9: Frontend — dynamic tiebreaker columns

**Files:**
- Modify: `frontend/src/api/report.ts`
- Modify: `frontend/src/api/report.test.ts`
- Modify: `frontend/src/routes/Report.tsx`
- Modify: `frontend/src/routes/Report.test.tsx`

**Interfaces:**
- Consumes: the new `TiebreakValue` wire shape from Task 8 (`{label, value, format}`)
- Produces: `StandingRow.tiebreakers: TiebreakValue[]` (frontend type); `Report.tsx` renders column headers/values from that array instead of hardcoded indices

- [ ] **Step 1: Update `frontend/src/api/report.test.ts` for the new shape**

```typescript
import { describe, expect, it, vi } from "vitest";
import { fetchPodReport } from "./report";

function fetchReturning(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({ ok: true, status, json: () => Promise.resolve(body) });
}

describe("report api", () => {
  it("fetchPodReport GETs /pods/:id/report", async () => {
    const apiFetch = fetchReturning({
      is_complete: false,
      rounds_played: 2,
      is_partial: true,
      active_entry_count: 1,
      recommended_rounds: 3,
      standings: [
        {
          entry_id: "e1",
          points: 6,
          rank: 1,
          tiebreakers: [
            { label: "OMW%", value: 0.75, format: "percent" },
            { label: "OOMW%", value: 0.5, format: "percent" },
          ],
        },
      ],
    });

    const report = await fetchPodReport(apiFetch, "pod-1");

    expect(report.standings[0].tiebreakers).toEqual([
      { label: "OMW%", value: 0.75, format: "percent" },
      { label: "OOMW%", value: 0.5, format: "percent" },
    ]);
    expect(apiFetch).toHaveBeenCalledWith("/pods/pod-1/report", undefined);
  });
});
```

- [ ] **Step 2: Run the frontend test to verify it fails**

Run: `cd frontend && npm test -- --run report.test.ts`
Expected: FAIL — `report.ts`'s `StandingRow.tiebreakers` type is still `number[]`; TypeScript compile error surfaces as a Vitest failure (type mismatch on the fixture literal, or the test still passes structurally but Task 3's later assertions won't — confirm by checking `npx tsc --noEmit` also fails).

Run: `cd frontend && npx tsc --noEmit`
Expected: FAIL — type error on `report.test.ts`'s new fixture shape against the old `tiebreakers: number[]` interface.

- [ ] **Step 3: Update `frontend/src/api/report.ts`**

```typescript
import { apiRequest, type ApiFetch } from "./request";

export interface TiebreakValue {
  label: string;
  value: number;
  format: "percent";
}

export interface StandingRow {
  entry_id: string;
  points: number;
  rank: number;
  tiebreakers: TiebreakValue[];
}

export interface PodReport {
  is_complete: boolean;
  rounds_played: number;
  is_partial: boolean;
  active_entry_count: number;
  recommended_rounds: number;
  standings: StandingRow[];
}

export function fetchPodReport(apiFetch: ApiFetch, podId: string): Promise<PodReport> {
  return apiRequest(apiFetch, `/pods/${podId}/report`);
}
```

- [ ] **Step 4: Run the frontend test to verify it passes**

Run: `cd frontend && npx tsc --noEmit && npm test -- --run report.test.ts`
Expected: PASS

- [ ] **Step 5: Update `frontend/src/routes/Report.test.tsx` fixtures for the new shape**

Replace `COMPLETE_REPORT`:

```typescript
const COMPLETE_REPORT = {
  is_complete: true,
  rounds_played: 2,
  is_partial: false,
  active_entry_count: 2,
  recommended_rounds: 3,
  standings: [
    {
      entry_id: "e1",
      points: 6,
      rank: 1,
      tiebreakers: [
        { label: "OMW%", value: 0.75, format: "percent" },
        { label: "OOMW%", value: 0.5, format: "percent" },
      ],
    },
    {
      entry_id: "e2",
      points: 3,
      rank: 2,
      tiebreakers: [
        { label: "OMW%", value: 0.415, format: "percent" },
        { label: "OOMW%", value: 0.4, format: "percent" },
      ],
    },
  ],
};
```

Update the `"shows OMW%/OOMW% columns"` test's name and body to reflect that the labels now come from the response (rename to make clear it's testing dynamic rendering, not hardcoded columns):

```typescript
  it("shows tiebreaker columns and values from the API response labels", async () => {
    server.use(
      http.get("/pods/pod-1/report", () => HttpResponse.json(COMPLETE_REPORT)),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();

    const rows = await screen.findAllByRole("row");
    expect(rows[0]).toHaveTextContent("OMW%");
    expect(rows[0]).toHaveTextContent("OOMW%");
    expect(rows[1]).toHaveTextContent("75.0%");
    expect(rows[1]).toHaveTextContent("50.0%");
    expect(rows[2]).toHaveTextContent("41.5%");
    expect(rows[2]).toHaveTextContent("40.0%");
  });
```

Add a new test proving the columns are genuinely dynamic (append near it):

```typescript
  it("renders Pokemon-labeled tiebreaker columns for a pokemon-tcg pod", async () => {
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
      http.get("/pods/pod-1/report", () =>
        HttpResponse.json({
          ...COMPLETE_REPORT,
          standings: COMPLETE_REPORT.standings.map((row) => ({
            ...row,
            tiebreakers: row.tiebreakers.map((tb, i) => ({
              ...tb,
              label: i === 0 ? "Op Win%" : "Op Op Win%",
            })),
          })),
        }),
      ),
      http.get("/entries", () => HttpResponse.json(ENTRIES)),
    );

    renderReport();

    const rows = await screen.findAllByRole("row");
    expect(rows[0]).toHaveTextContent("Op Win%");
    expect(rows[0]).toHaveTextContent("Op Op Win%");
  });
```

- [ ] **Step 6: Run the Report route tests to verify the updated/new ones fail**

Run: `cd frontend && npm test -- --run Report.test.tsx`
Expected: FAIL — `Report.tsx` still renders hardcoded `OMW%`/`OOMW%` headers and reads `tiebreakers[0]`/`[1]` as raw numbers, so the Pokemon-labeled test fails (headers stay "OMW%"/"OOMW%" regardless of response) and the existing test's assertions on `tiebreakers[0] * 100` break against the new object shape (`NaN%`).

- [ ] **Step 7: Update `frontend/src/routes/Report.tsx`'s table rendering**

Replace the `<thead>`/`<tbody>` block:

```tsx
          {report.standings.length === 0 ? (
            <p>No standings yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left">
                  <th className="py-1 pr-4">Rank</th>
                  <th className="py-1 pr-4">Entry</th>
                  <th className="py-1 pr-4">Points</th>
                  {report.standings[0].tiebreakers.map((tb) => (
                    <th key={tb.label} className="py-1 pr-4">
                      {tb.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {report.standings.map((row) => (
                  <tr key={row.entry_id} className="border-b border-gray-100">
                    <td className="py-1 pr-4">{row.rank}</td>
                    <td className="py-1 pr-4">{displayNameFor(entriesQuery.data, row.entry_id)}</td>
                    <td className="py-1 pr-4">{row.points}</td>
                    {row.tiebreakers.map((tb) => (
                      <td key={tb.label} className="py-1 pr-4">
                        {(tb.value * 100).toFixed(1)}%
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
```

- [ ] **Step 8: Run the Report route tests to verify they pass**

Run: `cd frontend && npx tsc --noEmit && npm test -- --run Report.test.tsx`
Expected: PASS (all tests)

- [ ] **Step 9: Run the full frontend suite**

Run: `cd frontend && npm test -- --run`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add frontend/src/api/report.ts frontend/src/api/report.test.ts frontend/src/routes/Report.tsx frontend/src/routes/Report.test.tsx
git commit -m "feat(frontend): render tiebreaker columns/labels from the API response (#57)"
```

---

### Task 10: TOM cross-validation acceptance tests (FR28/FR29 gate)

**Files:**
- Create: `backend/tests/acceptance/__init__.py`
- Create: `backend/tests/acceptance/tom_fixtures.py`
- Create: `backend/tests/acceptance/test_pokemon_tom_cross_validation.py`

**Interfaces:**
- Consumes: `SwissFormat`, `PokemonTiebreak`, `Entry`/`Match`/`MatchResult`/`Round` models; the two committed TOM XML fixtures at `docs/superpowers/fixtures/tom-tournaments/`
- Produces: `load_tom_pod(xml_path, pod_category) -> tuple[list[Entry], list[Round], dict[str, uuid.UUID]]`; `load_tom_standings(xml_path, standings_category, id_map) -> list[uuid.UUID]`

- [ ] **Step 1: Create the empty `__init__.py`**

```bash
touch backend/tests/acceptance/__init__.py
```

- [ ] **Step 2: Write `backend/tests/acceptance/tom_fixtures.py` (the parser — not a test file itself, no `test_` prefix so pytest won't collect it)**

```python
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from app.models import Entry, Match, MatchResult, Round

_OUTCOME_RESULT = {
    "1": MatchResult.ENTRY1_WIN,
    "2": MatchResult.ENTRY2_WIN,
    "3": MatchResult.TIE,
}


def load_tom_pod(
    xml_path: Path, pod_category: str
) -> tuple[list[Entry], list[Round], dict[str, uuid.UUID]]:
    """Parse a TOM export's <pod category=pod_category> into Entry/Round
    fixtures for PokemonTiebreak/SwissFormat.

    Returns (entries, rounds, userid_to_entry_id) so callers can translate
    TOM userids from <standings> into the same Entry.id values used here.
    """
    root = ET.parse(xml_path).getroot()
    id_map: dict[str, uuid.UUID] = {}

    def entry_id_for(userid: str) -> uuid.UUID:
        return id_map.setdefault(userid, uuid.uuid4())

    dropped_at_round: dict[str, int] = {}
    for player_el in root.find("players"):
        userid = player_el.get("userid")
        dropped_round_el = player_el.find("dropped/round")
        if dropped_round_el is not None:
            dropped_at_round[userid] = int(dropped_round_el.text)

    pod_el = next(pod for pod in root.find("pods") if pod.get("category") == pod_category)
    pod_id = uuid.uuid4()

    entries: list[Entry] = []
    for player_el in pod_el.find("subgroups/subgroup/players"):
        userid = player_el.get("userid")
        entries.append(
            Entry(
                id=entry_id_for(userid),
                pod_id=pod_id,
                player_uuid=uuid.uuid4(),
                source_system="tom-import",
                metadata_={},
                dropped_at_round=dropped_at_round.get(userid),
            )
        )

    rounds: list[Round] = []
    for round_el in pod_el.find("rounds"):
        matches: list[Match] = []
        for match_el in round_el.find("matches"):
            outcome = match_el.get("outcome")
            if outcome == "5":
                bye_userid = match_el.find("player").get("userid")
                matches.append(
                    Match(
                        id=uuid.uuid4(),
                        round_id=uuid.uuid4(),
                        entry1_id=entry_id_for(bye_userid),
                        entry2_id=None,
                        result=MatchResult.UNREPORTED,
                    )
                )
                continue

            player1_userid = match_el.find("player1").get("userid")
            player2_userid = match_el.find("player2").get("userid")
            matches.append(
                Match(
                    id=uuid.uuid4(),
                    round_id=uuid.uuid4(),
                    entry1_id=entry_id_for(player1_userid),
                    entry2_id=entry_id_for(player2_userid),
                    result=_OUTCOME_RESULT[outcome],
                )
            )

        round_ = Round(id=uuid.uuid4(), pod_id=pod_id, number=int(round_el.get("number")))
        round_.matches = matches
        rounds.append(round_)

    return entries, rounds, id_map


def load_tom_standings(
    xml_path: Path, standings_category: str, id_map: dict[str, uuid.UUID]
) -> list[uuid.UUID]:
    """Parse a TOM export's finished <standings><pod category=...> block
    into an Entry.id list ordered by place ascending, translated through
    id_map (from load_tom_pod) so it's directly comparable to a
    SwissFormat.compute_standings() result's entry_id order."""
    root = ET.parse(xml_path).getroot()
    standings_pod = next(
        pod
        for pod in root.find("standings")
        if pod.get("category") == standings_category and pod.get("type") == "finished"
    )
    placed = sorted(standings_pod.findall("player"), key=lambda el: int(el.get("place")))
    return [id_map[player_el.get("id")] for player_el in placed]
```

- [ ] **Step 3: Write the failing acceptance tests**

```python
# backend/tests/acceptance/test_pokemon_tom_cross_validation.py
from pathlib import Path

from app.formats.swiss import SwissFormat
from app.tiebreak.pokemon import PokemonTiebreak
from tests.acceptance.tom_fixtures import load_tom_pod, load_tom_standings

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "docs" / "superpowers" / "fixtures" / "tom-tournaments"


def test_round_rock_final_ranking_matches_tom_standings():
    """Primary fixture: 23->18 players, 1 bye (round 1), 5 drops, no ties.
    Covers the bye-denominator rule and the floor/cap end to end, including
    a dropped entry (5829175) that must still outrank two active entries."""
    xml_path = FIXTURES_DIR / "round-rock-summer-2026-06-20.xml"
    entries, rounds, id_map = load_tom_pod(xml_path, pod_category="0")
    expected_order = load_tom_standings(xml_path, standings_category="0", id_map=id_map)

    standings = SwissFormat(tiebreak=PokemonTiebreak()).compute_standings(entries, rounds)

    assert [row.entry_id for row in standings] == expected_order


def test_cg_league_night_masters_subset_ranking_matches_tom_standings():
    """Secondary fixture: 16-player age-combined pod (category 10), no bye,
    2 drops (one testing the floor, one testing the cap from the other
    direction), and one genuine tie (round 2) -- closes the tie-numerator
    open item from docs/pokemon-tiebreak-research.md. Op Win%/Op Op Win%
    are computed over the full 16-player pod (opponents can be outside the
    Masters division under age-combined pairing), then filtered down to
    the 12-player Masters (category 2) subset for the ranking comparison,
    since TOM only publishes final standings per division."""
    xml_path = FIXTURES_DIR / "cg-league-night-2026-07-28.xml"
    entries, rounds, id_map = load_tom_pod(xml_path, pod_category="10")
    expected_masters_order = load_tom_standings(xml_path, standings_category="2", id_map=id_map)

    standings = SwissFormat(tiebreak=PokemonTiebreak()).compute_standings(entries, rounds)

    masters_ids = set(expected_masters_order)
    actual_masters_order = [row.entry_id for row in standings if row.entry_id in masters_ids]

    assert actual_masters_order == expected_masters_order
```

- [ ] **Step 4: Run tests to verify they fail (or reveal a real formula/fixture mismatch)**

Run: `cd backend && .venv/bin/python -m pytest tests/acceptance -v`
Expected: initial run may FAIL with an `ImportError` if `tests` isn't importable as a package from the acceptance dir — if so, verify `backend/tests/__init__.py` already exists (it does; confirmed during planning) and that `pyproject.toml`'s `testpaths = ["tests"]` picks up the new directory automatically (no config change needed). Once import-clean, either both tests PASS immediately (implementation already correct) or a genuine mismatch surfaces — see Step 5.

- [ ] **Step 5: If a mismatch surfaces, diagnose against the handbook and fixture, not by adjusting the test to fit**

This is real ground-truth data, not a hand-computed fixture — a failure here means either (a) an implementation bug in `PokemonTiebreak`/`_rank_entries` from Tasks 3/4/7, or (b) a wrong assumption in `docs/pokemon-tiebreak-research.md` (most likely the §9 open items: the tie-numerator interpretation or the literal-vs-reconciled "total rounds" reading). Use `superpowers:systematic-debugging` if a mismatch isn't immediately attributable. Do not special-case the test to match an unexplained result.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/acceptance -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Run the full backend suite one more time**

Run: `cd backend && .venv/bin/python -m pytest tests -v`
Expected: PASS — full regression check before moving to documentation.

- [ ] **Step 8: Commit**

```bash
git add backend/tests/acceptance/__init__.py backend/tests/acceptance/tom_fixtures.py backend/tests/acceptance/test_pokemon_tom_cross_validation.py
git commit -m "test(acceptance): cross-validate PokemonTiebreak against real TOM tournament exports (FR28/FR29 gate)"
```

---

### Task 11: Documentation updates

**Files:**
- Modify: `REQUIREMENTS.md`
- Modify: `CHANGELOG.md`
- No test — documentation only; verify by reading the diff.

**Interfaces:** none (docs only)

- [ ] **Step 1: Update `REQUIREMENTS.md`'s FR28 row**

Find the FR28 row (currently: `| FR28 | Pokémon tiebreak strategy: Op Win% / Op Op Win% chain per the handbook §5.3.3 — 25% floor (not MTG's 33%), 100% max win% for completed entries vs. 75% max for dropped entries (depends on FR24's drop tracking), bye rounds excluded from a competitor's own win% when that competitor is later used as someone else's Op Win% input (§5.3.3.1) — a different bye nuance than FR25's bye-floor treatment | BR1, BR4 | 18 |`) and replace the description with the resolved (non-hedged) wording, matching `docs/pokemon-tiebreak-research.md`:

```
| FR28 | Pokémon tiebreak strategy: Op Win% / Op Op Win% chain per the handbook §5.3.3/§5.3.3.1 — 25% floor (not MTG's 33%), win% capped at 100% for entries that completed the tournament vs. 75% for entries that dropped (`Entry.dropped_at_round`, FR24), bye rounds count as a win in the numerator but are excluded from the rounds-played denominator (§5.6.1) — see `docs/pokemon-tiebreak-research.md` for the full reconciliation | BR1, BR4 | 18 |
```

- [ ] **Step 2: Add the MVP2 `CHANGELOG.md` entry**

`CHANGELOG.md` currently has an empty `## [Unreleased]` section (no MVP2 heading yet — this is the first MVP2 entry). Add:

```markdown
## [Unreleased]

### Added

- Pokémon tiebreak strategy: Op Win%/Op Op Win% chain with 25% floor,
  100%/75% completed-vs-dropped cap, and bye-denominator handling per the
  Play! Pokémon Tournament Rules Handbook, plus a head-to-head pairwise
  fallback tiebreaker, both behind the existing pluggable
  `TiebreakStrategy` interface (Phase 18, FR28/FR29)
- Labeled, typed tiebreaker wire contract (`{label, value, format}` per
  entry) replacing the bare unlabeled `list[float]`, so the Report screen
  renders the correct column headers for whichever game a pod is running
  (Phase 18, closes #57)
```

- [ ] **Step 3: Verify the diff**

Run: `git diff REQUIREMENTS.md CHANGELOG.md`
Expected: shows exactly the FR28 row rewording and the new CHANGELOG entry, no unrelated changes.

- [ ] **Step 4: Commit**

```bash
git add REQUIREMENTS.md CHANGELOG.md
git commit -m "docs: resolve FR28's bye-nuance hedge language, add MVP2 CHANGELOG entry for FR28/FR29/#57"
```

---

### Task 12: File the narrower follow-up issue, close #100, run full verification

**Files:** none — GitHub issue + verification only.

- [ ] **Step 1: File the narrower follow-up issue**

```bash
gh issue create \
  --title "Pokemon tiebreak: re-confirm tie-numerator and head-to-head DQ/no-show edge cases against official rulings" \
  --body "$(cat <<'EOF'
Narrower follow-up to #100 (closed by docs/pokemon-tiebreak-research.md and
the Phase 18 TOM cross-validation acceptance tests, see PR for this issue's
originating phase).

Two open items from docs/pokemon-tiebreak-research.md §9 that the two TOM
fixtures used in Phase 18's acceptance tests could not fully settle by
inspection:

1. Tie-numerator interpretation: the implementation treats a tie the same
   way OwpOomwTiebreak already does (match points / (win_points * rounds
   played), so a tie contributes fractional credit) and this was validated
   against a real tie in the cg-league-night fixture. If a future TOM
   export or an official Play! Pokemon ruling shows a different intended
   behavior, revisit PokemonTiebreak._own_win_pct.
2. Head-to-head "played each other" scope for DQ/no-show cases (handbook
   §5.5.1.1's Final Tiebreaker): neither fixture contains a DQ or no-show
   match, so PokemonTiebreak.break_tie()'s "decisive result" branch has
   not been exercised against that specific case. Re-confirm against
   Play! Pokemon's official FAQ/rulings, or a future TOM export that
   contains one, before assuming the current implementation is correct
   for that edge case.

Not blocking -- the current implementation is validated against real
tournament data for every case both fixtures exercise.
EOF
)"
```

- [ ] **Step 2: Close issue #100**

```bash
gh issue close 100 --comment "Resolved by docs/pokemon-tiebreak-research.md (Phase 18) plus the TOM cross-validation acceptance tests in this phase's PR, which validate the research doc's conclusions against real tournament data. Narrower remaining open items filed separately."
```

- [ ] **Step 3: Run the full backend and frontend suites one final time**

Run: `cd backend && .venv/bin/python -m pytest tests -v`
Expected: PASS (full suite)

Run: `cd frontend && npx tsc --noEmit && npm test -- --run`
Expected: PASS (full suite)

- [ ] **Step 4: Manual verification checklist (per CLAUDE.md's mandatory pre-merge gate)**

Bring up the backend (`cd backend && .venv/bin/uvicorn app.main:app --reload`) and frontend (`cd frontend && npm run dev`) locally, then walk this checklist:

- [ ] Create a `pokemon-tcg` pod, add 4+ entries, generate rounds, report results including at least one tie — confirm the Report screen shows "Op Win%"/"Op Op Win%" column headers (not "OMW%"/"OOMW%").
- [ ] Create a `generic` pod with the same flow — confirm it still shows "OMW%"/"OOMW%" (no regression).
- [ ] Drop an entry mid-pod (`dropped_at_round` set) in a `pokemon-tcg` pod, finish the pod, confirm its Op Win%/Op Op Win% values look capped relative to an otherwise-identical undropped entry (75% vs 100% ceiling).
- [ ] Force a genuine 2-way tie in final standings (same points, same Op Win%, same Op Op Win%) where the two entries played each other — confirm the match winner ranks above the loser in the final report, not UUID order.
- [ ] `curl /pods/{id}/report` directly for both a `pokemon-tcg` and `generic` pod — confirm the JSON `tiebreakers` field is `[{label, value, format}, ...]` in both, with game-appropriate labels.

- [ ] **Step 5: Report results**

Summarize pass/fail per checklist item back to the user before presenting PR/merge options — do not claim the phase complete until this manual pass is done, per CLAUDE.md's Manual Verification gate.

---

## Notes for the executor

- This plan is one phase (Phase 18) but is large — per CLAUDE.md's PR guardrail (≤~600 changed lines, split if larger), check `git diff main --stat` after Task 8 (the natural backend/wire-contract boundary) and again after Task 10 (acceptance tests). If either checkpoint's cumulative diff exceeds ~600 lines, stop and ask the owner whether to split into multiple PRs (e.g. "PR1: Tasks 1-7 tiebreak core", "PR2: Tasks 8-9 wire contract + frontend", "PR3: Tasks 10-12 TOM acceptance + docs") rather than deciding unilaterally.
- Do not run `gh pr merge` or push to `main` without explicit, in-the-moment owner approval — this applies per PR if the phase is split.
- The two TOM fixtures already committed to this branch contain real (anonymized) tournament data — do not add any further real player data to this repo without the same anonymization pass documented in `docs/superpowers/fixtures/tom-tournaments/README.md`.
