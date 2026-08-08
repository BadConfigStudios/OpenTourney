# Phase 8 — Swiss Real Tiebreakers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `SwissFormat`'s UUID-string tiebreak stopgap with real Swiss
tiebreakers (OMW%/OOMW%) computed via a pluggable `TiebreakStrategy`
interface, and surface the values through the report API and UI.

**Architecture:** New `backend/app/tiebreak/` package defines a
`TiebreakStrategy` ABC and its first implementation, `OwpOomwTiebreak`
(Family A — opponent-average percentage chain). `TournamentFormat` takes a
strategy via constructor injection; `SwissFormat` defaults to
`OwpOomwTiebreak()`. `_rank_entries` folds the computed tiebreak tuple into
its sort key between match points and the UUID last-resort. `StandingRow`/
`StandingRowRead` gain a `tiebreakers` field threaded through unchanged by
the report endpoint. Frontend adds two read-only columns to `Report.tsx`.

**Tech Stack:** Python/FastAPI/SQLAlchemy backend, pytest + testcontainers
(Postgres) for integration tests; React/TypeScript frontend, vitest + msw
for component tests.

## Global Constraints

- MVP1 instantiates `OwpOomwTiebreak` with MTG-standard defaults: floor
  `0.33`, `win_points=3`, `tie_points=1`, `loss_points=0` — matching
  `swiss.py`'s existing `WIN_POINTS`/`TIE_POINTS`/`LOSS_POINTS`.
- `TiebreakStrategy.compute` receives ALL entries and the FULL round
  history (not just one entry's own matches) — a future Family B strategy
  needs a player's own round-by-round sequence, not just opponents' final
  records.
- Return shape is `dict[uuid.UUID, tuple[float, ...]]`, most-significant
  value first — Family A returns `(omw_pct, oomw_pct)` — so ranking code
  can compare tuples lexicographically without knowing the strategy.
- UUID string comparison remains the absolute last-resort sort key, never
  removed — it is still needed when every computed tiebreak value ties
  (e.g. two undefeated entries in round 1 who share no common opponents
  yet).
- Byes: count toward the *receiving* entry's own points and rounds-played
  denominator (a bye is a win), but a bye is never added to anyone's
  *opponents-faced* list — nobody "played" a bye.
- Out of scope (do not implement): a Family B / cumulative strategy
  (tracked under issue #41), the 4-engine architectural restructuring, and
  fixing the greedy-pairing rematch gap (issue #12).
- Spec: `docs/superpowers/specs/2026-08-05-phase-8-swiss-tiebreakers-design.md`.
  Requirement: FR25, `REQUIREMENTS.md`.

---

## Task 1: `TiebreakStrategy` interface + `OwpOomwTiebreak` implementation

**Files:**
- Create: `backend/app/tiebreak/__init__.py` (empty package marker, matches `backend/app/formats/__init__.py`)
- Create: `backend/app/tiebreak/base.py`
- Create: `backend/app/tiebreak/owp_oomw.py`
- Test: `backend/tests/unit/test_owp_oomw_tiebreak.py`
- Modify: `DECISIONS.md` (append)

**Interfaces:**
- Produces: `TiebreakStrategy` (ABC, `backend/app/tiebreak/base.py`) with
  abstract method `compute(self, entries: Sequence[Entry], rounds: Sequence[Round]) -> dict[uuid.UUID, tuple[float, ...]]`.
- Produces: `OwpOomwTiebreak(floor: float = 0.33, win_points: int = 3, tie_points: int = 1, loss_points: int = 0)`
  (`backend/app/tiebreak/owp_oomw.py`), implementing `compute` returning
  `dict[uuid.UUID, tuple[float, float]]` (`(omw_pct, oomw_pct)`).
- Consumes: `app.models.Entry`, `app.models.Round`, `app.models.MatchResult` (existing).

- [ ] **Step 1: Write the failing unit tests**

```python
# backend/tests/unit/test_owp_oomw_tiebreak.py
import uuid

import pytest

from app.models import Entry, Match, MatchResult, Round
from app.tiebreak.owp_oomw import OwpOomwTiebreak


def _entry() -> Entry:
    return Entry(
        id=uuid.uuid4(),
        pod_id=uuid.uuid4(),
        player_uuid=uuid.uuid4(),
        source_system="test",
        metadata_={},
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


def test_floor_engages_for_a_weak_opponent():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY1_WIN)])

    tiebreaks = OwpOomwTiebreak().compute([a, b], [round1])

    # b has 0 points from 1 round played -> own MWP would be 0.0, floored to 0.33.
    # a's only opponent is b, so a's OMW% is exactly that floored value.
    assert tiebreaks[a.id][0] == pytest.approx(0.33)


def test_bye_counts_toward_own_denominator_but_is_never_an_opponent():
    a, b, c = _entry(), _entry(), _entry()
    round1 = _round(1, [_match(a, None), _match(b, c, MatchResult.ENTRY1_WIN)])
    round2 = _round(2, [_match(a, b, MatchResult.ENTRY1_WIN)])

    tiebreaks = OwpOomwTiebreak().compute([a, b, c], [round1, round2])

    # a's own record includes the bye: 2 wins (bye + round2 vs b) / 2 rounds
    # played = own MWP 1.0 -- the bye counts toward a's own denominator.
    # But a's only *opponent* across both rounds is b (round2) -- the bye
    # round never adds a phantom opponent, so OMW%(a) is exactly b's own
    # MWP, averaged over a single opponent, not two.
    b_own_mwp = max(3 / (3 * 2), 0.33)  # b: round1 win (3) + round2 loss (0) / 2 rounds
    assert tiebreaks[a.id][0] == pytest.approx(b_own_mwp)


def test_oomw_averages_opponents_omw_percentages():
    a, b, c, d = _entry(), _entry(), _entry(), _entry()
    round1 = _round(
        1,
        [
            _match(a, b, MatchResult.ENTRY1_WIN),
            _match(c, d, MatchResult.ENTRY1_WIN),
        ],
    )
    round2 = _round(2, [_match(a, c, MatchResult.ENTRY2_WIN)])  # c beats a

    tiebreaks = OwpOomwTiebreak().compute([a, b, c, d], [round1, round2])

    # a: 3 pts / 2 rounds = 0.5 own MWP. c: 6 pts / 2 rounds = 1.0 own MWP.
    # b's only opponent is a -> OMW%(b) = 0.5. d's only opponent is c -> OMW%(d) = 1.0.
    # a's opponents are b and c -> OOMW%(a) averages OMW%(b) and OMW%(c).
    omw_b = 0.5
    omw_c = max(6 / (3 * 2), 0.33)
    assert tiebreaks[a.id][1] == pytest.approx((omw_b + omw_c) / 2)


def test_custom_point_values_and_floor_are_respected():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY1_WIN)])

    tiebreaks = OwpOomwTiebreak(floor=0.5, win_points=2, tie_points=1, loss_points=-1).compute(
        [a, b], [round1]
    )

    # b's own MWP with these constants: -1 / (2 * 1) = -0.5, floored to 0.5.
    assert tiebreaks[a.id][0] == pytest.approx(0.5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/unit/test_owp_oomw_tiebreak.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.tiebreak'`)

- [ ] **Step 3: Write the interface**

```python
# backend/app/tiebreak/base.py
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
        entry's own matches) so a future Family B strategy can read any
        player's own round-by-round result sequence, not only opponents'
        final records.
        """
```

```python
# backend/app/tiebreak/__init__.py
```

- [ ] **Step 4: Write the `OwpOomwTiebreak` implementation**

```python
# backend/app/tiebreak/owp_oomw.py
import uuid
from collections.abc import Sequence

from app.models import Entry, MatchResult, Round
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
        points, rounds_played = self._points_and_rounds_played(rounds)
        opponents = self._opponents_faced(rounds)

        own_mwp = {
            entry.id: self._own_mwp(points.get(entry.id, 0), rounds_played.get(entry.id, 0))
            for entry in entries
        }
        omw_pct = {
            entry.id: self._average(own_mwp, opponents.get(entry.id, []))
            for entry in entries
        }
        oomw_pct = {
            entry.id: self._average(omw_pct, opponents.get(entry.id, []))
            for entry in entries
        }

        return {entry.id: (omw_pct[entry.id], oomw_pct[entry.id]) for entry in entries}

    def _own_mwp(self, points: int, rounds_played: int) -> float:
        if rounds_played == 0:
            return 0.0
        return max(points / (self.win_points * rounds_played), self.floor)

    @staticmethod
    def _average(values: dict[uuid.UUID, float], opponent_ids: list[uuid.UUID]) -> float:
        if not opponent_ids:
            return 0.0
        return sum(values[opponent_id] for opponent_id in opponent_ids) / len(opponent_ids)

    def _points_and_rounds_played(
        self, rounds: Sequence[Round]
    ) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
        points: dict[uuid.UUID, int] = {}
        rounds_played: dict[uuid.UUID, int] = {}

        for round_ in rounds:
            for match in round_.matches:
                if match.entry2_id is None:
                    points[match.entry1_id] = points.get(match.entry1_id, 0) + self.win_points
                    rounds_played[match.entry1_id] = rounds_played.get(match.entry1_id, 0) + 1
                    continue

                rounds_played[match.entry1_id] = rounds_played.get(match.entry1_id, 0) + 1
                rounds_played[match.entry2_id] = rounds_played.get(match.entry2_id, 0) + 1

                if match.result is MatchResult.ENTRY1_WIN:
                    points[match.entry1_id] = points.get(match.entry1_id, 0) + self.win_points
                    points[match.entry2_id] = points.get(match.entry2_id, 0) + self.loss_points
                elif match.result is MatchResult.ENTRY2_WIN:
                    points[match.entry2_id] = points.get(match.entry2_id, 0) + self.win_points
                    points[match.entry1_id] = points.get(match.entry1_id, 0) + self.loss_points
                elif match.result is MatchResult.TIE:
                    points[match.entry1_id] = points.get(match.entry1_id, 0) + self.tie_points
                    points[match.entry2_id] = points.get(match.entry2_id, 0) + self.tie_points
                else:
                    raise ValueError(f"round {round_.number} has an unreported match")

        return points, rounds_played

    @staticmethod
    def _opponents_faced(rounds: Sequence[Round]) -> dict[uuid.UUID, list[uuid.UUID]]:
        opponents: dict[uuid.UUID, list[uuid.UUID]] = {}

        for round_ in rounds:
            for match in round_.matches:
                if match.entry2_id is None:
                    continue
                opponents.setdefault(match.entry1_id, []).append(match.entry2_id)
                opponents.setdefault(match.entry2_id, []).append(match.entry1_id)

        return opponents
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/unit/test_owp_oomw_tiebreak.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Log the technical decision**

Append to `DECISIONS.md`:

```markdown
## 2026-08-05 — Phase 8: pluggable `TiebreakStrategy` interface, Family A only this phase

`SwissFormat`'s standings/pairing tiebreak was a UUID-string comparison
stopgap since Phase 6. Replacing it with real Swiss tiebreakers (OMW%/OOMW%)
via a hardcoded formula inside `swiss.py` would work for MVP1 but block the
roadmap's ruleset-module generalization (issue #41) once a second game
module needs a structurally different tiebreak (e.g. Flesh and Blood's
round-history-based CMP, identified in `docs/tcg-ruleset-research.md` as a
second algorithm "family," not just different constants). Introduced a
`TiebreakStrategy` interface (`backend/app/tiebreak/`) that receives all
entries and the full round history — not just one entry's own matches —
so a future Family B strategy fits the same contract without a breaking
change. `TournamentFormat` takes the strategy via constructor injection;
`SwissFormat` defaults to `OwpOomwTiebreak()` (MTG-standard constants).
Phase 8 ships only the Family A (opponent-average percentage chain)
implementation; a second family is deferred to #41, triggered by an actual
second game module needing it, not spread speculatively now. Confirmed
with the owner 2026-08-05.
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/tiebreak/__init__.py backend/app/tiebreak/base.py backend/app/tiebreak/owp_oomw.py backend/tests/unit/test_owp_oomw_tiebreak.py DECISIONS.md
git commit -m "feat(backend): add pluggable TiebreakStrategy + OwpOomwTiebreak (FR25)"
```

---

## Task 2: Wire `OwpOomwTiebreak` into `SwissFormat`

**Files:**
- Modify: `backend/app/formats/base.py`
- Modify: `backend/app/formats/swiss.py`
- Test: `backend/tests/unit/test_swiss_format.py` (extend, no existing test bodies change)

**Interfaces:**
- Consumes: `TiebreakStrategy` (Task 1, `backend/app/tiebreak/base.py`), `OwpOomwTiebreak` (Task 1, `backend/app/tiebreak/owp_oomw.py`).
- Produces: `TournamentFormat.__init__(self, tiebreak: TiebreakStrategy)` sets `self.tiebreak`.
- Produces: `StandingRow.tiebreakers: tuple[float, ...]` field (positional, no default — every call site must supply it).
- Produces: `_rank_entries(entries, standings, tiebreaks)` (new third parameter; existing internal callers in `swiss.py` are updated in this task).

- [ ] **Step 1: Write the failing unit test for `_rank_entries`**

Append to `backend/tests/unit/test_swiss_format.py`:

```python
def test_rank_entries_orders_by_points_then_tiebreak_then_uuid():
    from app.formats.swiss import _rank_entries

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
    )

    # e_tied_a/e_tied_b (6 pts) rank above e_high_tiebreak/e_low_tiebreak
    # (3 pts) despite a lower tiebreak value -- points always wins first.
    assert {r.id for r in ranked[:2]} == {e_tied_a.id, e_tied_b.id}
    # Within the 3-point group, the higher tiebreak value ranks first.
    assert ranked[2].id == e_high_tiebreak.id
    assert ranked[3].id == e_low_tiebreak.id
    # e_low_points is last regardless of its (unused) high tiebreak value.
    assert ranked[4].id == e_low_points.id
    # e_tied_a/e_tied_b are tied on both points AND tiebreak -- UUID string
    # order is the last-resort fallback.
    assert [r.id for r in ranked[:2]] == sorted([e_tied_a.id, e_tied_b.id], key=str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_swiss_format.py::test_rank_entries_orders_by_points_then_tiebreak_then_uuid -v`
Expected: FAIL (`_rank_entries() takes 2 positional arguments but 3 were given`)

- [ ] **Step 3: Add `tiebreakers` to `StandingRow` and inject the strategy into `TournamentFormat`**

```python
# backend/app/formats/base.py
import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from app.models import Entry, Round
from app.tiebreak.base import TiebreakStrategy


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
    tiebreakers: tuple[float, ...]


class TournamentFormat(ABC):
    slug: str

    def __init__(self, tiebreak: TiebreakStrategy):
        self.tiebreak = tiebreak

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

- [ ] **Step 4: Wire the strategy into `SwissFormat`**

In `backend/app/formats/swiss.py`, add the import and give `SwissFormat` a
constructor, then update `generate_round`, `compute_standings`, and
`_rank_entries`:

```python
from app.tiebreak.base import TiebreakStrategy
from app.tiebreak.owp_oomw import OwpOomwTiebreak
```

```python
class SwissFormat(TournamentFormat):
    slug = "swiss"

    def __init__(self, tiebreak: TiebreakStrategy | None = None):
        super().__init__(tiebreak or OwpOomwTiebreak())

    def generate_round(
        self, entries: Sequence[Entry], previous_rounds: Sequence[Round]
    ) -> list[Pairing]:
        if not previous_rounds:
            return _pair_round_one(entries)

        standings, bye_used = _compute_standings(entries, previous_rounds)
        tiebreaks = self.tiebreak.compute(entries, previous_rounds)
        already_paired = _paired_history(previous_rounds)
        ranked = _rank_entries(entries, standings, tiebreaks)

        bye_entry = None
        if len(ranked) % 2 == 1:
            bye_entry = _select_bye_entry(ranked, bye_used)
            ranked = [entry for entry in ranked if entry.id != bye_entry.id]

        pairings = _pair_remaining(ranked, already_paired)
        if bye_entry is not None:
            pairings.append(Pairing(entry1_id=bye_entry.id, entry2_id=None))

        return _assign_tables(pairings)

    def compute_standings(
        self, entries: Sequence[Entry], rounds: Sequence[Round]
    ) -> list[StandingRow]:
        standings, _ = _compute_standings(entries, rounds)
        tiebreaks = self.tiebreak.compute(entries, rounds)
        ranked = _rank_entries(entries, standings, tiebreaks)
        return [
            StandingRow(
                entry_id=entry.id,
                points=standings.get(entry.id, 0),
                rank=i + 1,
                tiebreakers=tiebreaks.get(entry.id, ()),
            )
            for i, entry in enumerate(ranked)
        ]
```

```python
def _rank_entries(entries: Sequence[Entry], standings: dict, tiebreaks: dict) -> list:
    return sorted(
        entries,
        key=lambda entry: (
            -standings.get(entry.id, 0),
            tuple(-v for v in tiebreaks.get(entry.id, ())),
            str(entry.id),
        ),
    )
```

- [ ] **Step 5: Run the new test, then the full existing suite**

Run: `cd backend && pytest tests/unit/test_swiss_format.py -v`
Expected: PASS (all tests, including the pre-existing ones — they exercise
`SwissFormat` through `generate_round`/`compute_standings` only, and the
scenarios already happen to produce the same pairings/order once real
tiebreaks are computed, per the worked examples in the design spec).

- [ ] **Step 6: Commit**

```bash
git add backend/app/formats/base.py backend/app/formats/swiss.py backend/tests/unit/test_swiss_format.py
git commit -m "feat(backend): wire OwpOomwTiebreak into SwissFormat ranking (FR25)"
```

---

## Task 3: Surface tiebreakers through the report API

**Files:**
- Modify: `backend/app/schemas/report.py`
- Modify: `backend/app/routers/pods.py`
- Test: `backend/tests/integration/test_report_flow_api.py` (extend)

**Interfaces:**
- Consumes: `StandingRow.tiebreakers` (Task 2, `backend/app/formats/base.py`).
- Produces: `StandingRowRead.tiebreakers: list[float]` — the report API's
  public contract, consumed by the frontend in Task 4.

- [ ] **Step 1: Write the failing integration test**

Append to `backend/tests/integration/test_report_flow_api.py` (add `import pytest` at the top alongside the existing `import uuid`):

```python
def test_report_ranks_by_omw_when_match_points_tie(api_client, make_token):
    """A real tiebreak scenario (not a coincidental UUID tie): two entries
    finish with equal match points but faced different-strength opponents,
    so OMW% -- not entry-id string comparison -- must decide rank order."""
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    for _ in range(4):
        _add_entry(api_client, token, pod_id)

    def _report(match_id: str, winner_id: str, entry1_id: str) -> None:
        result = "entry1_win" if winner_id == entry1_id else "entry2_win"
        response = api_client.post(
            f"/matches/{match_id}/result",
            json={"result": result, "method": "manual_entry"},
            headers=_auth_headers(token),
        )
        assert response.status_code == 200

    round1 = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    match1, match2 = round1["matches"]
    w1, l1 = match1["entry1_id"], match1["entry2_id"]
    w2, l2 = match2["entry1_id"], match2["entry2_id"]
    _report(match1["id"], winner_id=w1, entry1_id=match1["entry1_id"])
    _report(match2["id"], winner_id=w2, entry1_id=match2["entry1_id"])

    round2 = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    winners_match = next(
        m for m in round2["matches"] if {m["entry1_id"], m["entry2_id"]} == {w1, w2}
    )
    losers_match = next(
        m for m in round2["matches"] if {m["entry1_id"], m["entry2_id"]} == {l1, l2}
    )
    # w2 takes the winners' match (climbing to 2-0); w1 falls to 1-1.
    _report(winners_match["id"], winner_id=w2, entry1_id=winners_match["entry1_id"])
    # l1 takes the losers' match (climbing to 1-1); l2 stays 0-2.
    _report(losers_match["id"], winner_id=l1, entry1_id=losers_match["entry1_id"])

    report = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token)).json()
    standings = {row["entry_id"]: row for row in report["standings"]}

    # w1 and l1 both sit at 3 points (1 win, 1 loss), but w1's loss was to
    # w2 (a 6-point, 2-0 opponent) while l1's loss was to w1 (a 3-point
    # opponent) -- w1 faced the stronger average opponent, so OMW% must
    # rank it above l1 despite the equal points.
    assert standings[w1]["points"] == standings[l1]["points"] == 3
    assert len(standings[w1]["tiebreakers"]) == 2
    assert standings[w1]["tiebreakers"][0] == pytest.approx(0.75)
    assert standings[l1]["tiebreakers"][0] == pytest.approx(0.415)
    assert standings[w1]["rank"] < standings[l1]["rank"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/integration/test_report_flow_api.py::test_report_ranks_by_omw_when_match_points_tie -v`
Expected: FAIL (`KeyError: 'tiebreakers'`) — requires Docker running locally (testcontainers spins up Postgres).

- [ ] **Step 3: Add `tiebreakers` to the schema and pass it through the endpoint**

```python
# backend/app/schemas/report.py
import uuid

from pydantic import BaseModel


class StandingRowRead(BaseModel):
    entry_id: uuid.UUID
    points: int
    rank: int
    tiebreakers: list[float]


class PodReport(BaseModel):
    is_complete: bool
    rounds_played: int
    is_partial: bool
    standings: list[StandingRowRead]
```

In `backend/app/routers/pods.py`, update the `StandingRowRead` construction
inside `get_pod_report` (the only call site):

```python
        standings=[
            StandingRowRead(
                entry_id=row.entry_id,
                points=row.points,
                rank=row.rank,
                tiebreakers=list(row.tiebreakers),
            )
            for row in standings
        ],
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/integration/test_report_flow_api.py -v`
Expected: PASS (all tests in the file, including the pre-existing partial/complete flow test — it doesn't assert on `tiebreakers`, so the new required field doesn't break it)

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && pytest --cov=app`
Expected: PASS, no regressions in `test_pods_api.py`, `test_rounds_api.py`, `test_matches_api.py`, `test_pairings_flow_api.py`, `test_pod_model.py`, `test_pod_roles_api.py`

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/report.py backend/app/routers/pods.py backend/tests/integration/test_report_flow_api.py
git commit -m "feat(backend): surface OMW%/OOMW% tiebreakers through the report API (FR25)"
```

---

## Task 4: Surface OMW%/OOMW% in the Report screen

**Files:**
- Modify: `frontend/src/api/report.ts`
- Modify: `frontend/src/routes/Report.tsx`
- Modify: `frontend/src/api/report.test.ts`
- Modify: `frontend/src/routes/Report.test.tsx`

**Interfaces:**
- Consumes: `PodReport.standings[].tiebreakers: number[]` from
  `GET /pods/{id}/report` (Task 3) — `tiebreakers[0]` is OMW%,
  `tiebreakers[1]` is OOMW%, per the backend's `(omw_pct, oomw_pct)` tuple
  order.

- [ ] **Step 1: Write the failing API-layer test**

Update `frontend/src/api/report.test.ts`:

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
      standings: [{ entry_id: "e1", points: 6, rank: 1, tiebreakers: [0.75, 0.5] }],
    });

    const report = await fetchPodReport(apiFetch, "pod-1");

    expect(report).toEqual({
      is_complete: false,
      rounds_played: 2,
      is_partial: true,
      standings: [{ entry_id: "e1", points: 6, rank: 1, tiebreakers: [0.75, 0.5] }],
    });
    expect(apiFetch).toHaveBeenCalledWith("/pods/pod-1/report", undefined);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/report.test.ts`
Expected: FAIL (TypeScript compile error under `tsc --noEmit` / the `toEqual` still passes at runtime since JS doesn't enforce the type, but the build step in Step 6 will fail until `StandingRow` gains the field — run `npx tsc --noEmit` here to see it fail explicitly)

- [ ] **Step 3: Add `tiebreakers` to the frontend type**

```typescript
// frontend/src/api/report.ts
import { apiRequest, type ApiFetch } from "./request";

export interface StandingRow {
  entry_id: string;
  points: number;
  rank: number;
  tiebreakers: number[];
}

export interface PodReport {
  is_complete: boolean;
  rounds_played: number;
  is_partial: boolean;
  standings: StandingRow[];
}

export function fetchPodReport(apiFetch: ApiFetch, podId: string): Promise<PodReport> {
  return apiRequest(apiFetch, `/pods/${podId}/report`);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/api/report.test.ts`
Expected: PASS

- [ ] **Step 5: Write the failing component test**

Update `frontend/src/routes/Report.test.tsx`: change `COMPLETE_REPORT`'s
standings to include `tiebreakers`, and add a new test for the columns.

```typescript
const COMPLETE_REPORT = {
  is_complete: true,
  rounds_played: 2,
  is_partial: false,
  standings: [
    { entry_id: "e1", points: 6, rank: 1, tiebreakers: [0.75, 0.5] },
    { entry_id: "e2", points: 3, rank: 2, tiebreakers: [0.415, 0.4] },
  ],
};
```

Add after the "shows ranked standings..." test:

```typescript
  it("shows OMW%/OOMW% columns", async () => {
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

- [ ] **Step 6: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/routes/Report.test.tsx`
Expected: FAIL (`OMW%` text not found)

- [ ] **Step 7: Add the columns to `Report.tsx`**

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
                  <th className="py-1 pr-4">OMW%</th>
                  <th className="py-1">OOMW%</th>
                </tr>
              </thead>
              <tbody>
                {report.standings.map((row) => (
                  <tr key={row.entry_id} className="border-b border-gray-100">
                    <td className="py-1 pr-4">{row.rank}</td>
                    <td className="py-1 pr-4">{displayNameFor(entriesQuery.data, row.entry_id)}</td>
                    <td className="py-1 pr-4">{row.points}</td>
                    <td className="py-1 pr-4">{(row.tiebreakers[0] * 100).toFixed(1)}%</td>
                    <td className="py-1">{(row.tiebreakers[1] * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
```

(Only the `<thead>` row and the `<td>` list inside the `.map` change —
everything else in `Report.tsx` is untouched.)

- [ ] **Step 8: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/routes/Report.test.tsx`
Expected: PASS (all tests in the file — the pre-existing tests use
`toHaveTextContent` substring checks, unaffected by the two extra columns)

- [ ] **Step 9: Run the full frontend suite and typecheck**

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npx eslint .`
Expected: PASS, no regressions

- [ ] **Step 10: Commit**

```bash
git add frontend/src/api/report.ts frontend/src/api/report.test.ts frontend/src/routes/Report.tsx frontend/src/routes/Report.test.tsx
git commit -m "feat(frontend): show OMW%/OOMW% columns on the Report screen (FR25)"
```

---

## Self-Review Notes

**Spec coverage:**
- §2 Tiebreak interface → Task 1.
- §3 Wiring into `SwissFormat` → Task 2.
- §4 API and frontend surfacing → Tasks 3–4.
- §5 Testing plan (acceptance/integration/unit, floor, byes, OOMW%, UUID
  fallback) → covered across Task 1 (`OwpOomwTiebreak` unit tests), Task 2
  (`_rank_entries` unit test incl. UUID fallback), Task 3 (real-API tie
  scenario). This repo has no separate `tests/acceptance/` layer — its
  existing "flow" integration tests (`test_pairings_flow_api.py`,
  `test_report_flow_api.py`) already serve as the acceptance layer per
  `[[feedback_phase_workflow]]`-style convention from prior phases, so
  Task 3 extends `test_report_flow_api.py` rather than adding a new file.
- §6 Follow-ups (Family B, 4-engine restructuring) → intentionally not
  planned; captured in Global Constraints as out of scope.

**Note on manual verification:** per this repo's mandatory pre-merge gate,
after all 4 tasks are implemented and reviewed, bring up the local dev
stack (recipe in `[[project_opentourney_phase7]]` memory: docker Postgres +
`alembic upgrade head` + minted JWTs + `uvicorn` + `vite`) and exercise a
real tied-standings scenario through the actual Pairings/Report UI in a
browser before presenting merge options — this plan's automated tests
prove the formula and wiring, not the rendered screen.
