# Phase 8 — Swiss Real Tiebreakers (Design)

Date: 2026-08-05
Status: Approved (brainstorming), pending plan/execution
Requirement: FR25, `REQUIREMENTS.md` Build Order phase 8
Related: `docs/opentourney-architecture.md` (4-engine lifecycle model — this
phase implements the Stats-Engine-shaped piece only, no restructuring),
`docs/tcg-ruleset-research.md` (tiebreaker algorithm family research across
5 non-Pokemon TCGs), roadmap issue #41 (ruleset module interface
generalization — this phase is a down payment on that interface, not its
full scope)

---

## 1. Scope

MVP1's `SwissFormat` currently breaks standings/pairing ties by comparing
entry UUID strings (`backend/app/formats/swiss.py` `_rank_entries`) —
accepted as a stopgap in Phase 6 ("already randomly generated, so it's as
good as anything as a tiebreaker"). This phase replaces that with real
Swiss tiebreakers: **OMW%** (Opponents' Match-Win Percentage) and **OOMW%**
(Opponents' OMW%), the MTG/Lorcana-family formula identified in
`tcg-ruleset-research.md` as "Family A — opponent-average percentage
chain."

**In scope:**
- A pluggable `TiebreakStrategy` interface, general enough to also fit
  Family B (cumulative/round-history, e.g. Flesh and Blood's CMP) without
  a breaking change later — but Phase 8 ships only the Family A
  implementation.
- `OwpOomwTiebreak`: the Family A implementation, parameterized (floor
  value, win/tie/loss point values) rather than hardcoded — MVP1
  instantiates it with MTG-standard defaults (0.33 floor, 3/1/0 points,
  matching `swiss.py`'s existing `WIN_POINTS`/`TIE_POINTS`/`LOSS_POINTS`).
- Wiring the strategy into both pairing order (`generate_round`) and final
  standings (`compute_standings`) via one shared call site.
- Surfacing OMW%/OOMW% through the report API and UI.

**Out of scope (explicitly deferred):**
- Any second tiebreak family (Family B / CMP) — tracked under #41, not
  this phase.
- Restructuring the codebase toward the 4-engine model
  (`opentourney-architecture.md`) — no "Stats Engine" module boundary is
  extracted; the strategy plugs into the existing `TournamentFormat`
  interface as-is.
- Fixing the known greedy-pairing rematch-avoidance gap (issue #12) —
  unrelated, pre-existing.
- UUID tiebreak is not removed entirely — it remains the absolute
  last-resort sort key when two entries are tied on every computed
  tiebreak value (e.g. two undefeated entries who haven't played common
  opponents yet, round 1 pairing).

---

## 2. Tiebreak interface

New package `backend/app/tiebreak/`:

```python
# backend/app/tiebreak/base.py
class TiebreakStrategy(ABC):
    @abstractmethod
    def compute(
        self, entries: Sequence[Entry], rounds: Sequence[Round]
    ) -> dict[uuid.UUID, tuple[float, ...]]:
        """Per-entry ordered tiebreak chain, most-significant value first.

        Receives ALL entries and the full round history (not just one
        entry's own matches) so a future Family B strategy can read any
        player's own round-by-round result sequence, not only opponents'
        final records — Family A and Family B need different slices of
        the same input, not different inputs.
        """
```

Return shape is a tuple, not a single float, so both families fit the same
contract: Family A returns `(omw_pct, oomw_pct)`; a future Family B
strategy returns `(cmp,)`. Ranking code compares these tuples
lexicographically after match points, so a strategy can express a chain of
any length without changing the caller.

```python
# backend/app/tiebreak/owp_oomw.py
class OwpOomwTiebreak(TiebreakStrategy):
    def __init__(
        self,
        floor: float = 0.33,
        win_points: int = 3,
        tie_points: int = 1,
        loss_points: int = 0,
    ):
        ...

    def compute(
        self, entries: Sequence[Entry], rounds: Sequence[Round]
    ) -> dict[uuid.UUID, tuple[float, float]]:
        # 1. own_mwp[entry] = points_earned / (win_points * rounds_played),
        #    floored at `floor` if lower.
        # 2. omw_pct[entry] = average(own_mwp[opponent] for each opponent
        #    faced, excluding byes).
        # 3. oomw_pct[entry] = average(omw_pct[opponent] for each opponent
        #    faced, excluding byes).
        ...
```

Bye handling: a bye counts toward the *receiving* entry's own match points
(win) and rounds-played denominator, but is excluded when computing
*other* entries' OMW%/OOMW% (a bye has no real MWP to contribute to an
opponent's average) — matching `tcg-ruleset-research.md`'s documented MTG
rule.

---

## 3. Wiring into `SwissFormat`

`TournamentFormat` takes the strategy via constructor injection:

```python
class TournamentFormat(ABC):
    def __init__(self, tiebreak: TiebreakStrategy):
        self.tiebreak = tiebreak
```

`SwissFormat.__init__` defaults to `OwpOomwTiebreak()` (MTG-standard
constants). The existing call site (`backend/app/routers/pods.py`,
`SwissFormat()`) needs no change — the default argument absorbs it.

`_rank_entries` takes the computed tiebreak dict:

```python
def _rank_entries(entries, standings, tiebreaks):
    return sorted(entries, key=lambda e: (
        -standings.get(e.id, 0),
        tuple(-v for v in tiebreaks.get(e.id, ())),
        str(e.id),  # last-resort only
    ))
```

Both `generate_round` (pairing order) and `compute_standings` (final
report) call `self.tiebreak.compute(entries, previous_rounds)` once and
pass the result into `_rank_entries` — one shared computation, no
duplicated logic between pairing and reporting, satisfying FR25's "without
touching pairing/report code" intent when a future strategy is swapped
in.

`StandingRow` (`backend/app/formats/base.py`) gains a field:

```python
@dataclass(frozen=True)
class StandingRow:
    entry_id: uuid.UUID
    points: int
    rank: int
    tiebreakers: tuple[float, ...]
```

---

## 4. API and frontend surfacing

`StandingRowRead` (`backend/app/schemas/report.py`) gains:

```python
class StandingRowRead(BaseModel):
    entry_id: uuid.UUID
    points: int
    rank: int
    tiebreakers: list[float]  # e.g. [omw_pct, oomw_pct]
```

`PodReport` is otherwise unchanged. `pods.py`'s report endpoint passes
`row.tiebreakers` through unmodified.

Frontend `Report.tsx` (Phase 7 PR4): standings table gains OMW%/OOMW%
columns, formatted as percentages, sourced directly from the new API
field. No new endpoint. No change to sort order (already backend-driven)
or to `Pairings.tsx` (pairing order isn't player-visible beyond table
number).

---

## 5. Testing plan

Per this repo's TDD + testing-layers rules, boundary-crossing order is
acceptance → integration → unit, each confirmed RED before its GREEN.

- **Acceptance**: extend the existing pairing/report end-to-end test with
  a scenario where match points alone don't resolve rank (a real tiebreak
  scenario, not a coincidental tie) — confirms the Organizer-facing final
  report ranks by OMW%/OOMW%, not UUID.
- **Integration** (`backend/tests/test_report_flow_api.py`, extending the
  Phase 7 PR4 test): seed such a bracket via the real API, hit
  `GET /pods/{id}/report`, assert the `tiebreakers` field is present and
  drives the returned rank order.
- **Unit** (`backend/tests/test_owp_oomw_tiebreak.py`): `OwpOomwTiebreak`
  in isolation — floor engages correctly (a very weak opponent's MWP is
  raised to `floor`, not left lower), byes excluded from opponents'
  averages but counted in the bye-receiver's own MWP denominator, OOMW%
  correctly averages opponents' OMW% values, two entries tied on every
  computed value still require the UUID fallback.
- **Unit** (`backend/tests/test_swiss_format.py`, extending existing
  coverage): `_rank_entries` sorts correctly given a fixed, injected
  tiebreak dict — verifies sort-tuple construction independent of the real
  formula.

---

## 6. Follow-ups (not this phase)

- Family B (cumulative/round-history) tiebreak strategy — tracked under
  #41, triggered by a second game module (e.g. Flesh and Blood, if ever
  pursued) actually needing it.
- 4-engine restructuring (`opentourney-architecture.md`) — revisit once a
  second `TournamentFormat`/`GameModule` combination exists to validate
  the boundary against, not speculatively now.
