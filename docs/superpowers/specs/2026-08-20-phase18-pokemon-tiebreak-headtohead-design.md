# Phase 18 — Pokémon Tiebreak Strategy + Head-to-Head Fallback (FR28, FR29)

Design for FR28 and FR29 (see `REQUIREMENTS.md`). Extends the pluggable
`TiebreakStrategy` interface introduced in Phase 8 (FR25) with a second
strategy family (Pokémon's Op Win%/Op Op Win% chain) and a pairwise
head-to-head fallback. Also folds in issue #57 (tiebreak wire contract has no
label/strategy identifier), since #57 explicitly called for landing alongside
whatever PR introduces a second `TiebreakStrategy` family — this phase is
that PR.

Research basis: `docs/pokemon-tiebreak-research.md` (handbook §5.3.2, §5.3.3,
§5.3.3.1, §5.5.1.1, §5.6.1, §5.5.6), closing issue #100.

## Current state (Phase 17 / pre-Phase-18)

- `backend/app/tiebreak/base.py`: `TiebreakStrategy` ABC, `compute(entries, rounds) -> dict[uuid.UUID, tuple[float, ...]]`.
- `backend/app/tiebreak/owp_oomw.py`: `OwpOomwTiebreak` (Family A, MTG-style: floor=0.33, no cap, bye excluded from the *averaging* step).
- `backend/app/formats/swiss.py`: `SwissFormat.__init__` hardcodes `OwpOomwTiebreak(win/tie/loss=MVP1 constants)` as its default — one shared instance for every pod regardless of game.
- `backend/app/formats/registry.py`: `FORMATS: dict[str, TournamentFormat] = {"swiss": SwissFormat()}` — a single static singleton, no `game_slug` awareness.
- `backend/app/games/base.py`: `GameModule` ABC, only `validate_entry_metadata`.
- `backend/app/games/pokemon.py`: `PokemonGameModule` exists (Phase 17, FR27) with `WIN_POINTS`/`TIE_POINTS`/`LOSS_POINTS` class attrs, but they are **not wired into the pairing/scoring engine** — its own docstring says "see Phase 18, FR28/FR29."
- `backend/app/schemas/report.py`: `StandingRowRead.tiebreakers: list[float]` — bare, unlabeled (issue #57).
- `frontend/src/routes/Report.tsx`: hardcodes `tiebreakers[0]`/`[1]` as "OMW%"/"OOMW%" column headers.

## Architecture

- `TiebreakStrategy` (base.py) gains two methods:
  - `break_tie(entry_a_id, entry_b_id, rounds) -> int | None` — default `None` (no pairwise capability). Only `PokemonTiebreak` overrides it.
  - `labels() -> tuple[str, ...]` — matches `compute()`'s tuple order; drives the wire-contract labels (#57).
- `GameModule` (games/base.py) gains abstract `tiebreak_strategy() -> TiebreakStrategy`.
  - `GenericGameModule` returns `OwpOomwTiebreak(win/tie/loss=its existing constants)`.
  - `PokemonGameModule` returns `PokemonTiebreak(win/tie/loss=its existing constants)`.
- New `backend/app/ruleset.py`: `Ruleset` frozen dataclass (`format: TournamentFormat`, `game_module: GameModule`) + `get_ruleset_or_422(pod) -> Ruleset` factory. Builds `SwissFormat(tiebreak=game_module.tiebreak_strategy())` per `(format_slug, game_slug)`.
  - Replaces `formats/registry.py`'s static `SwissFormat()` singleton **only at the `pods.py` call site** (round generation, standings/report) — the one place tiebreak actually matters.
  - `entries.py`'s existing `get_game_module` call (metadata validation) is untouched — it never needs a tiebreak strategy.
- New `backend/app/tiebreak/pokemon.py`: `PokemonTiebreak(TiebreakStrategy)`, sibling to `OwpOomwTiebreak` (not a subclass — different enough math it'd be more confusing to inherit than duplicate the small amount of shared structure via extraction below).
  - `floor = 0.25` (handbook §5.3.3.1, vs MTG's 0.33).
  - Own-win% caps at **1.0 if the entry completed the tournament, 0.75 if `entry.dropped_at_round is not None`** (§5.3.3.1) — uses FR24's existing `Entry.dropped_at_round` field.
  - Own-win% numerator counts a bye as a win; denominator **excludes** any bye round from "rounds played" (§5.6.1, see `docs/pokemon-tiebreak-research.md` §3 for the full reconciliation of §5.3.3.1 vs §5.6.1). This is a real behavior difference from `OwpOomwTiebreak`, which includes the bye round in its own-MWP denominator and instead excludes the bye *opponent* from the averaging step.
  - `break_tie()`: pairwise head-to-head (see below).
  - `labels()` returns `("Op Win%", "Op Op Win%")`.
- Shared point/opponent-tallying helpers (`_points_and_rounds_played`, `_opponents_faced`, `_average`) extracted from `owp_oomw.py` into `backend/app/tiebreak/_shared.py`, used by both strategies unmodified. `_points_and_rounds_played` gains a `bye_rounds_played: bool = True` parameter — `OwpOomwTiebreak` calls it with the default (bye counts as a played round); `PokemonTiebreak` calls it with `False` (bye round excluded from the played-rounds denominator, per §5.6.1). `OwpOomwTiebreak` itself is otherwise untouched — zero regression risk to the existing MTG/generic path.
- `_rank_entries` (`swiss.py`): primary sort unchanged — `(-points, tuple(-tiebreak_values))`. New second pass: group entries by identical `(points, tiebreak-tuple)` key. For a group of **exactly 2**, call `self.tiebreak.break_tie(a, b, rounds)` — a resolved result reorders the pair. For `None` or groups of **3+**, fall through unchanged to the existing `str(entry.id)` last-resort tail-break (this stands in for the handbook's "randomly determined" — same deterministic-not-random approach FR25 already uses for its own last-resort, not a new pattern introduced here).

## FR28 — Pokémon tiebreak math

`PokemonTiebreak.compute()` mirrors `OwpOomwTiebreak`'s two-step shape (own value floored/capped, *then* averaged into Op Win% / Op Op Win%) with these deltas, all sourced from `docs/pokemon-tiebreak-research.md`:

1. **Floor**: 0.25, not 0.33.
2. **Cap**: `1.0` if `entry.dropped_at_round is None`, `0.75` otherwise (§5.3.3.1). `OwpOomwTiebreak` has no cap at all — this is new logic, not a reused code path.
3. **Bye denominator**: own win% = (wins, bye counts as a win) / (rounds played, bye round excluded) — see `_shared.py`'s `bye_rounds_played` parameter above.
4. **Chain depth**: 2 levels (Op Win%, Op Op Win%) vs MTG's 4 (OMW%, GW%, OGW%) — Pokémon has no game-level (individual-game, as opposed to match) statistic. `compute()` returns a 2-tuple, matching `labels()`'s 2-tuple.

Cap is applied before the floor comparison: `max(floor, min(cap, raw_own_win_pct))`.

## FR29 — Head-to-head fallback

`PokemonTiebreak.break_tie(entry_a_id, entry_b_id, rounds)`:
- Scans `rounds` for a match between the two entries.
- If found with a decisive result (one entry won), returns which entry ranks higher.
- If no match exists between them, or the match that exists was a tie, returns `None`.

Per handbook §5.5.1.1's Final Tiebreaker, three branches, all handled by `_rank_entries`'s grouping pass (see Architecture above):
- Exactly 2 tied + they played and one won → winner ranks higher.
- Exactly 2 tied + they didn't play (or played and tied) → falls to the existing `str(id)` tail-break.
- 3+ tied → `break_tie()` is never called at all; falls straight to the tail-break. This matches the handbook precisely — head-to-head is skipped entirely once a third competitor shares the tie, even if pairwise results exist among subsets of that group.

## Wire contract (#57)

- `StandingRowRead.tiebreakers: list[float]` → `list[TiebreakValue]`, `TiebreakValue = {label: str, value: float, format: Literal["percent"]}`.
- Conversion happens at the `pods.py` router boundary using `strategy.labels()` zipped with the existing per-entry tuple — the internal `StandingRow.tiebreakers` (swiss.py) stays a plain `tuple[float, ...]`, no format-level change to the pairing/ranking internals.
- `frontend/src/api/report.ts`: type update to match the new shape.
- `frontend/src/routes/Report.tsx`: renders column headers and percent-formatting from the response instead of hardcoding `tiebreakers[0]`/`[1]` as "OMW%"/"OOMW%". Existing hardcoded-column tests convert to labeled-response fixtures — this is a breaking change to `Report.tsx`'s test fixtures, not just an addition, since the old bare-`list[float]` fixtures no longer match the schema.

## Testing

**Unit (backend):**
- `PokemonTiebreak`: floor, dropped-cap (0.75) vs completed-cap (1.0) boundary, bye-denominator exclusion, `break_tie()` (played+decisive / played+tie / not-played / — 3-way groups are `_rank_entries`'s concern, not `break_tie()`'s).
- `_shared.py` extraction: existing `OwpOomwTiebreak` unit tests pass unchanged — proves the extraction didn't alter Family A behavior.
- `_rank_entries`'s new grouping/tie-break pass, both strategies (`OwpOomwTiebreak` never calls `break_tie` since it returns `None`; `PokemonTiebreak` does).

**Integration (backend):**
- `/pods/{id}/report` returns labeled tiebreakers (`Op Win%`/`Op Op Win%`) for a `pokemon-tcg` pod vs (`OMW%`/`OOMW%`) for a `generic` pod.
- `get_ruleset_or_422` resolves the correct format+strategy per `(format_slug, game_slug)`; unrecognized `game_slug` still 422s the same way `get_game_module` already does.

**Frontend:**
- `Report.tsx` renders labels/format from the API response; existing hardcoded-column tests updated to labeled fixtures.

**Acceptance — TOM cross-validation** (real ground truth, not hand-computed):

Two real Tournament Operations Manager exports, saved at `docs/superpowers/fixtures/tom-tournaments/` (see that directory's README for full details and the TOM XML encoding notes — outcome codes, bye encoding, etc.):

1. **`round-rock-summer-2026-06-20.xml`** (primary) — 23→18 players, self-contained single pod, 3 rounds, 1 bye (round 1), 5 drops after round 1 with varied records. Covers the bye-denominator rule, both floor and cap, and validates real final ranking order end to end — including the case where a dropped player (5829175, 0-1 then dropped) finishes above two still-active players, which is a genuine ordering assertion, not just a formula-value check.
2. **`cg-league-night-2026-07-28.xml`** (secondary) — 12-player Masters subset of a 16-player age-combined event, 3 rounds, no bye, 2 drops (one 0-1 testing the floor, one 1-0 testing the cap boundary from the *other* direction — raw 100% capped down to 75%), one genuine tie (round 2, table 4, `outcome="3"`). Specifically closes the tie-numerator open item from the research doc, which the primary fixture can't test (no ties in it).

Test harness: parse each XML's `<players>`/`<rounds>`/`<match>` data into `Entry`/`Round`/`Match` fixtures, run `PokemonTiebreak.compute()` + `_rank_entries()` against them, and diff the resulting final rank order against the XML's `<standings>` block (final rank/place only — TOM's export doesn't carry its own computed Op Win%/Op Op Win% numbers, so this validates ranking order, not intermediate percentages; intermediate values are hand-derived from the handbook formula as a secondary sanity check, not diffed against TOM directly). Any mismatch is either an implementation bug or a wrong assumption in the research doc, and specifically resolves the research doc's open items on the tie-numerator and the literal-vs-reconciled reading of "total rounds" in §5.3.3.1.

This is the plan's final acceptance-test task, gating "FR28/FR29 done" — sequenced after the unit/integration layers so a TOM mismatch narrows to a specific formula step rather than the whole pipeline.

## Documentation updates

- `REQUIREMENTS.md` FR28: drop the "different bye nuance... (depends on further confirmation)" hedge language once bye handling is implemented per the resolved research doc.
- New follow-up issue (narrower than the now-closed #100): the two items the research doc still can't resolve purely by inspection even after the TOM cross-validation — specifically re-confirm against Play! Pokémon's official FAQ/rulings if a TOM edge case doesn't fully settle them (e.g., a DQ/no-show scoped "played each other" question for head-to-head, if neither fixture happens to exercise it).
- `CHANGELOG.md` entry under the MVP2 unreleased section for FR28/FR29/#57.
