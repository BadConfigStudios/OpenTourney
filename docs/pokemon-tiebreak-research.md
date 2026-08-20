# Pokémon TCG Tiebreak Research — Play! Pokémon Tournament Rules Handbook

Reference doc for OpenTourney's pluggable ruleset module. Companion to `docs/tcg-ruleset-research.md`, which covers MTG, Yu-Gi-Oh!, One Piece, Lorcana, and Flesh and Blood but explicitly excludes Pokémon ("has its own dedicated module") — leaving no written research doc for the Pokémon handbook sections FR28/FR29 depend on. This doc closes that gap (issue #100).

**Purpose:** capture the Play! Pokémon Tournament Rules Handbook's match-point, win-percentage, and tiebreaker rules precisely enough to implement FR28 (Pokémon tiebreak strategy) and FR29 (head-to-head fallback tiebreaker) without re-deriving them from memory. Every number below is a direct quote or close paraphrase of the handbook — not a guess.

**Source document:** Play! Pokémon Tournament Rules Handbook, English version, last revision **May 21, 2026**. Section numbers below (§5.3.2, §5.3.3, §5.3.3.1, §5.5.1.1, §5.6.1, §5.5.6) refer to this revision.

---

## Quick comparison

| | MTG / Lorcana (Family A, per `tcg-ruleset-research.md`) | Pokémon |
|---|---|---|
| Own-stat floor | 33% (MWP floored at 0.33) | **25%** (win % floored at 25%) |
| Own-stat cap | None documented | **100%** if tournament completed, **75%** if dropped early |
| Chain depth | 4 steps (match pts → OMW% → GW% → OGW%) | 3 steps (match pts → Op Win% → Op Op Win%) — no game-level step |
| Bye's effect on own stat | Bye excluded from the *average* (doesn't appear as an "opponent"); MWP itself is computed normally | Bye contributes to **neither** the numerator **nor** the denominator of the recipient's own win% used as an input to *other* competitors' Op Win%/Op Op Win% — see "Bye nuance" below, a different mechanism than MTG's, empirically corrected against real TOM tournament data during Phase 18 |
| Final fallback | Not covered in `tcg-ruleset-research.md` | **Head-to-head**, then random if no head-to-head result or 3+ still tied |

**Headline finding:** Pokémon's tiebreaker is the same *shape* as MTG/Lorcana's Family A (opponent-average percentage chain) — match points, then an average of opponents' win rates, then an average of opponents' opponents' win rates. But it differs in three concrete, implementation-relevant ways: (1) different floor constant (25% vs 33%), (2) an added cap that depends on whether the competitor completed the event or dropped (75% vs 100% — a distinction Family A as documented for MTG doesn't have), and (3) a bye-handling mechanism that excludes the bye round entirely (neither numerator nor denominator) from the bye recipient's own win% rather than excluding the bye from an *average* the way MTG does. It also has one additional pairwise tiebreaker (head-to-head) that isn't part of Family A's chain in the MTG/Lorcana doc at all.

---

## 1. Match structure and points

**Match structure:** Swiss rounds. At Championship Series events, Swiss rounds "may use single-game or best-of-three matches. This decision is at the discretion of the Organizer" (§5.5.6) — i.e., Bo1 is an organizer-configurable option, not fixed like MTG's Bo3.

**Points (§5.3.2):**
> Competitors receive three match points for a win, zero for a loss, and one for a tie.

Same point values as MTG/Lorcana (3/1/0), but note Pokémon's handbook text uses "tie" where MTG uses "draw" — same concept, different label; no formula difference implied.

**Source:** Play! Pokémon Tournament Rules Handbook §5.3.2, §5.5.6.

---

## 2. Opponents' Win Percentage (Op Win%)

**Definition (§5.3.3):**
> A competitor's opponents' win percentage—abbreviated to "Op Win %" on tournament documentation—is the average of the win percentages of all opponents played during a given set of rounds.

This is the direct analog of MTG's OMW% (Opponents' Match-Win Percentage): both are an *average of opponents' own win-rate figures*. The difference is in how each opponent's own win-rate figure ("win percentage," singular, not "win percentage of matches" — Pokémon has no separate game-level stat) is computed.

**Calculating an individual competitor's own win percentage (§5.3.3.1):**
> The total number of rounds an opponent completes determines how their win percentage is calculated.
>
> Please Note: In calculating the opponents' win percentage, rounds in which a competitor received a random bye do not count as a win for that competitor.
>
> If a competitor completes the tournament, their win percentage will be the number of wins divided by the total number of rounds in the tournament, with a minimum win percentage of 25% and a maximum win percentage of 100%.

Example table given in the handbook (5-round event):

| Wins | Rounds | Win % |
|---|---|---|
| 1 | 5 | 25% |
| 3 | 5 | 60% |
| 5 | 5 | 100% |

> If the competitor dropped from the event before it was completed, their win percentage is the number of wins divided by the number of rounds in which they participated, with a minimum win percentage of 25% and a maximum win percentage of 75%.

Example table given in the handbook (dropped competitor):

| Wins | Rounds played | Win % |
|---|---|---|
| 1 | 5 | 25% |
| 3 | 5 | 60% |
| 5 | 5 | 75% (capped — would be 100% uncapped) |

> Once a competitor's opponents' win percentages are calculated, they are averaged, resulting in the final figure that is displayed.

**Two-step shape, same as FR25's `OwpOomwTiebreak`:** compute each opponent's own win% first (with its own floor/cap applied), *then* average those already-floored/capped values into Op Win%. This mirrors FR25/MTG's "own-MWP floored, then averaged" structure — but with three concrete differences the ruleset module needs to model as config, not new algorithm shape:

1. Floor is **25%**, not MTG's 33%.
2. There is a **cap** at all (100% or 75%) — FR25's current implementation has no upper cap.
3. The cap value itself is **conditional on completed-vs-dropped status** (100% completed / 75% dropped) — a second axis FR25 doesn't have, and one that depends on FR24's drop tracking to know which value applies to a given competitor.

**Source:** Play! Pokémon Tournament Rules Handbook §5.3.3, §5.3.3.1.

---

## 3. The bye nuance — reconciling §5.3.3.1 and §5.6.1

This is the specific ambiguity FR28 flags, and it's worth stating precisely because the two sections read as contradictory in isolation.

**§5.3.3.1** says a completed competitor's win % is "the number of wins divided by the total number of rounds in the tournament," and separately notes (the "Please Note" callout) that "rounds in which a competitor received a random bye do not count as a win for that competitor" **when they appear as an input to someone else's Op Win % calculation.**

**§5.6.1 (Random Byes)** says:
> A bye counts as a win for that competitor's match record but does not count as a round played when calculating that competitor's win percentage. Where byes are inevitable, they will always be awarded to the competitor with the worst match record if at all possible. However, no competitor will ever receive more than one bye over the course of a tournament.

**Corrected conclusion (interpretation C, validated against real TOM tournament data during Phase 18 implementation):** a bye round contributes to **neither** the numerator **nor** the denominator of the bye recipient's own win percentage, for the specific purpose of that figure being used as an input to *other* competitors' Op Win%/Op Op Win% calculations. Only the competitor's actually-played (non-bye) rounds count for this figure. This does **not** affect the competitor's own primary standings *points* (used for the points-based ranking) — a bye still awards full match points there, per §5.3.2/§5.6.1's "counts as a win for that competitor's match record"; that's computed separately (`app.formats.swiss._compute_standings`) and is unaffected by this section.

This doc originally concluded the opposite — that a bye counts as a win in the numerator while only the denominator is adjusted ("interpretation A" below) — reading §5.6.1's "counts as a win for that competitor's match record" as extending into the win-percentage numerator itself. Two other readings were tested against real Tournament Operations Manager (TOM) exports (`docs/superpowers/fixtures/tom-tournaments/round-rock-summer-2026-06-20.xml`, a 23-entrant pod with one bye in round 1):

- **A (originally documented here):** bye counts as a win in the numerator, excluded only from the rounds-played denominator.
- **B (a literal §5.3.3.1 reading):** bye counts as both a win and a played round (denominator = total scheduled rounds).
- **C (corrected, current):** bye excluded entirely — neither numerator nor denominator.

The fixture contains a decisive pairwise case: two competitors, both 3-0 (9 match points), who never played each other (so the head-to-head fallback in §6 doesn't resolve the tie). TOM's published final standings rank one of them (`5252655`) strictly above the other (`5608492`). Under interpretations A and B, `5608492` computes a strictly *higher* Op Win%/Op Op Win% than `5252655` and should rank first — contradicting TOM. Under interpretation C, the bye recipient in `5608492`'s opponent chain (`5739819`) drops from an own-win% of 0.5 (A) / 0.333 (B) to 0.25 (floored under C, since excluding the bye round leaves them 0-2 in actual play), which pulls `5608492`'s Op Win% down below `5252655`'s — correctly matching TOM's order. Interpretation C reproduces TOM's exact order for every non-zero-point entry in the fixture (16 of 23 entries; the remaining discrepancies are a separate, unrelated dropped-entry anomaly — see the acceptance test's documented exclusion in `backend/tests/acceptance/test_pokemon_tom_cross_validation.py`, not a bye-handling issue).

Why the original A reading doesn't hold up: §5.6.1's "counts as a win for that competitor's match record" is best read as scoped to the competitor's own *match record* (i.e., their points/W-L tally for standings purposes, per §5.3.2) — not as extending into the separate win-percentage figure that §5.3.3.1 defines as an input to *other* competitors' calculations. The "Please Note" in §5.3.3.1 ("rounds in which a competitor received a random bye do not count as a win for that competitor") is, read on its own terms, a direct statement about the win-percentage numerator specifically — and real TOM software implements it that way: the bye round is dropped from the win-percentage calculation altogether, not partially retained via a numerator-only credit.

**Why this differs from FR25/MTG's bye handling:** FR25's `OwpOomwTiebreak` (per `tcg-ruleset-research.md` §1) excludes the bye "opponent" from the *averaging step* — a player who received a bye simply isn't counted as one of their opponents' opponents, and the bye's effect on the bye-recipient's own MWP is not separately adjusted (MWP is computed as match points / (3 × rounds played) with the bye round included as a played round worth full match points). Pokémon's mechanism instead excludes the bye round **from the bye recipient's own win% calculation entirely** — both numerator and denominator — before that win% is floored/capped and averaged into anyone else's Op Win%, which is a different place in the pipeline than where MTG's exclusion happens. A ruleset implementation that reuses FR25's "exclude bye from the average" logic verbatim for Pokémon would produce the wrong number: Pokémon needs the bye excluded from the *bye recipient's own win% inputs*, independent of who is averaging whom.

**Source:** Play! Pokémon Tournament Rules Handbook §5.3.3.1 (Please Note), §5.6.1; corrected against real TOM tournament data, Phase 18 (`docs/superpowers/fixtures/tom-tournaments/round-rock-summer-2026-06-20.xml`).

---

## 4. Opponents' Opponents' Win Percentage (Op Op Win%)

**Definition, from the Second Tiebreaker in §5.5.1.1:**
> A competitor's opponents' opponents' win percentage (Op Op Win %) is the average of the Op Win % of all that competitor's opponents.

Structurally this is the direct analog of MTG's OGW% step, except Pokémon's chain has no game-level statistic in between — it goes straight from Op Win% to an average of Op Win%'s (i.e., "opponents' Op Win%"), rather than MTG's four-step match/game interleaving (OMW% → GW% → OGW%). Net effect: Pokémon's chain is **3 levels deep** (match points → Op Win% → Op Op Win%) versus MTG's **4 levels** (match points → OMW% → GW% → OGW%).

**Source:** Play! Pokémon Tournament Rules Handbook §5.5.1.1 (Second Tiebreaker).

---

## 5. Final Placement in Swiss Standings — full tiebreaker chain

**§5.5.1.1**, in full:

> After the final round of Swiss, the only undefeated competitor—or competitor with the highest number of match points and the best tiebreakers—is the winner of the tournament. All other competitors are ranked based on their final records at the event.
>
> Because competitors often have a similar number of match points, Play! Pokémon uses tiebreakers to determine the final ranking of each competitor. After competitors are ranked by final match points, tiebreakers are applied in the following order. Once the criteria for one tiebreaker is met, no further tiebreakers are applied.

**Tiebreaker chain:**

1. **Match points** (primary ranking).
2. **First Tiebreaker — Opponents' Win Percentage**: "Competitors who are tied are ranked in order of their Op Win %, from highest to lowest."
3. **Second Tiebreaker — Opponents' Opponents' Win Percentage**: "Competitors who remain tied are now ranked in order of their Op Op Win %, from highest to lowest."
4. **Final Tiebreaker — Head-to-Head** (see §6 below).

**"Once the criteria for one tiebreaker is met, no further tiebreakers are applied"** — i.e., the chain short-circuits: if Op Win% alone breaks the tie between two competitors, Op Op Win% and head-to-head are never consulted for that pair. This matters for implementation — the strategy needs to resolve ties level-by-level within each still-tied group, not compute all levels up front and sort by a composite tuple (though a composite-tuple sort produces the same *ranking* as long as head-to-head is handled specially — see §6, since head-to-head isn't a scalar that sorts cleanly against ungrouped competitors).

**Source:** Play! Pokémon Tournament Rules Handbook §5.5.1.1.

---

## 6. Final Tiebreaker — Head-to-Head

**§5.5.1.1, Final Tiebreaker:**
> If exactly two competitors are tied in the final standings and those competitors played each other during the tournament, then the winner of that match is ranked higher than the loser. If exactly two competitors are tied in the final standings and those competitors did not play each other during the tournament, then the order in which they appear will be randomly determined. If more than two competitors are tied in the final standings, then the order in which they appear will be randomly determined.

This is a **pairwise**, not scalar, tiebreaker, and it only applies under a narrow condition: exactly two competitors remain tied after match points, Op Win%, and Op Op Win% all fail to separate them, **and** those two competitors played each other at some point in the tournament. Three explicit branches:

- Exactly 2 tied + they played each other → match winner ranked higher.
- Exactly 2 tied + they did **not** play each other → random.
- 3+ tied (regardless of who played whom) → random.

**Implementation implication for FR29:** because this is pairwise (needs "did these two specific competitors play each other, and who won") rather than an averaged scalar like Op Win%/Op Op Win%, `TiebreakStrategy`'s interface needs to support a fallback comparator that takes a *pair* of competitors and consults match history between them, not just a per-competitor numeric score. It's also the exact tiebreaker referenced by FR29 as extending the pluggable interface for a "pairwise fallback comparison." Note the 3+-tied case explicitly bypasses head-to-head entirely and goes straight to random — head-to-head is not attempted at all once a third competitor is in the tied group, even if pairwise head-to-head results exist among subsets of that group.

**Source:** Play! Pokémon Tournament Rules Handbook §5.5.1.1 (Final Tiebreaker).

---

## 7. Random Byes

**§5.6.1**, in full:
> A bye counts as a win for that competitor's match record but does not count as a round played when calculating that competitor's win percentage. Where byes are inevitable, they will always be awarded to the competitor with the worst match record if at all possible. However, no competitor will ever receive more than one bye over the course of a tournament.

Three distinct rules bundled in this section:

1. **Match-record effect:** bye = win, for match points and overall record purposes (standings points only — see §3's scoping note).
2. **Win%-calculation effect:** bye round excluded from *both* the numerator and the "rounds played" denominator when computing that competitor's own win% for use as an input to others' Op Win%/Op Op Win% (the corrected mechanism discussed in §3 above — interpretation C).
3. **Bye allocation policy:** byes go to the worst-record competitor when unavoidable, and no competitor gets more than one bye per tournament. (Allocation policy is a pairing-engine concern, not a tiebreaker-formula concern, but is included here since it's in the same handbook section and constrains what data the tiebreak module can assume — e.g., a given competitor's bye count is always 0 or 1, never more.)

**Source:** Play! Pokémon Tournament Rules Handbook §5.6.1.

---

## 8. Architectural implication for the ruleset module

Pokémon's tiebreaker fits `tcg-ruleset-research.md`'s **Family A** (opponent-average percentage chain) at the shape level — it is an averaging chain over opponents' own win-rate figures, not a round-history/cumulative system like Flesh and Blood's Family B. It should reuse Family A's general "own-stat floored, then averaged" strategy interface. But it cannot be adopted as pure config on top of the *MTG* instantiation of that strategy the way Lorcana can, because of three deltas:

1. **Different constants:** 25% floor (not 33%), plus a cap Family A as documented for MTG doesn't have at all (100%/75%).
2. **A conditional constant:** which cap applies (100% vs 75%) depends on the competitor's completed-vs-dropped status, which depends on FR24's drop tracking being available as an input to the tiebreak calculation — this is a second config axis, not just a different single floor value.
3. **A different bye mechanism:** MTG excludes the bye from the *averaging* step; Pokémon excludes the bye round entirely — neither numerator nor denominator — from the bye recipient's *own win% calculation* (interpretation C, §3). These are not interchangeable — implementing Pokémon's bye rule by copying MTG's "exclude bye from average" logic would compute the wrong Op Win% for anyone who faced a competitor who received a bye earlier in the event.

Additionally, Pokémon needs a **head-to-head pairwise fallback** (§6) that isn't part of Family A's chain as documented for MTG/Lorcana. This is the concern FR29 scopes out as extending `TiebreakStrategy` with a pairwise comparator, separate from the scalar Op Win%/Op Op Win% steps that FR28 covers. Recommendation: model FR28 as a Family-A-derived strategy with its own config object (floor=0.25, cap={completed:1.0, dropped:0.75}, bye-fully-excluded=true, chain-depth=2 i.e. Op Win% + Op Op Win% only, no game-level step), and model FR29 as a separate fallback strategy consumed by FR28's strategy when the percentage chain terminates in an unresolved tie, rather than trying to force head-to-head into the same scalar-averaging code path.

---

## 9. Open verification items

- [x] **RESOLVED (Phase 18, empirically):** whether "the total number of rounds in the tournament" in §5.3.3.1's completed-competitor case is meant literally (raw scheduled round count) or "rounds played" given §5.6.1's bye-exclusion language. Real TOM tournament data (`docs/superpowers/fixtures/tom-tournaments/round-rock-summer-2026-06-20.xml`) settles this in favor of "rounds actually played" — specifically, interpretation C (bye excluded from both numerator and denominator; see §3), reproducing TOM's exact final order for 16 of 23 entries including a decisive pairwise case (two never-met 3-0 competitors correctly ordered only under this reading). No further FAQ/ruling lookup needed.
- [ ] Confirm there is no game-level (best-of-3 individual-game) statistic anywhere in the Pokémon chain analogous to MTG's GW%/OGW% — the handbook sections provided here (§5.3.2, §5.3.3, §5.3.3.1, §5.5.1.1, §5.6.1, §5.5.6) don't mention one, but confirm against the full handbook table of contents in case a game-level stat exists elsewhere and simply wasn't surfaced in this excerpt.
- [ ] Confirm how a **tie** (not a loss) affects a competitor's own win% numerator — §5.3.3.1's wins/rounds formula and its example tables only show whole wins and don't demonstrate how a 1-match-point tie contributes to the "wins" numerator (full win, half win, or excluded like a bye). §5.3.2 establishes ties are possible (1 match point) but the win% formula in §5.3.3.1 isn't spelled out for that case in the text provided.
- [ ] Confirm what happens for a competitor whose *opponent* dropped mid-event with zero wins-so-far, or other edge cases at the boundary of the 25% floor and the completed/dropped cap split, directly against the handbook's example tables or a Play! Pokémon ruling, before finalizing FR28's implementation.
- [ ] Confirm the exact scope of "played" for head-to-head purposes in §5.5.1.1 — e.g., whether an intentional draw/tie between the two tied competitors, or a match that ended in a no-show/DQ, still counts as "played each other" for the head-to-head check, versus falling through to the random-order branch.
- [ ] Reconfirm all of the above against the current handbook revision at implementation time — Play! Pokémon revises this handbook periodically; this doc is pinned to the May 21, 2026 revision cited in Phase 17/18 planning materials.
