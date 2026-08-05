# TCG Ruleset Research — Match Formats & Tiebreaker Formulas

Reference doc for designing OpenTourney's pluggable ruleset module. Covers the top TCGs by market share, excluding Pokémon (which has its own dedicated module): Magic: The Gathering, Yu-Gi-Oh!, One Piece Card Game, Disney Lorcana, and Flesh and Blood.

**Purpose:** identify how many distinct tiebreaker *algorithms* (not just parameter sets) we actually need to support, so the ruleset interface is pluggable at the right level of abstraction — not so generic it can't express real differences, not so specific it can't be reused.

---

## Quick comparison

| Game | Swiss match format | Draws in Swiss? | Top cut format | Tiebreaker family |
|---|---|---|---|---|
| Magic: The Gathering | Best-of-3 | Yes (intentional or time-based) | Single-elim (historically Top 8) | Opponent-average % chain (OMW% → GW% → OGW%) |
| Yu-Gi-Oh! | Best-of-3 | No (removed in Tournament Policy v2.5, Sept 2025 — unresolved matches are now a double loss) | Single-elim, capped at Top 8 | Opponent-record based (similar shape to Pokémon's resistance system) |
| One Piece Card Game | **Best-of-1** | No (double loss on unresolved timeout; simultaneous-loss ties go to the turn-player as loser) | **Best-of-3**, Top 8 or Top 16 depending on attendance | Opponent-average %, exact public formula unconfirmed |
| Disney Lorcana | Best-of-3 | Yes | Single-elim Top 8 | Same family as MTG (OMW% → GW% → OGW%) |
| Flesh and Blood | **Best-of-1** | Yes (time-based) | **Best-of-1** Top 8, single-elim, untimed | **Cumulative Match Points (CMP)** — round-history based, structurally different from the % chain above |

**Headline finding:** four of five games share one tiebreaker *shape* (opponent-average percentage chain). Flesh and Blood does not — its primary tiebreaker needs the player's own round-by-round result history over time, not just opponents' final records. That's the one case that needs a genuinely different algorithm, not just different constants.

---

## 1. Magic: The Gathering

**Match structure:** Best-of-3 per round. Swiss followed by single-elimination Top 8 (format has varied historically — double-elim was used in some Magic Pro League–era digital formats).

**Points:** Match win = 3, draw = 1, loss = 0. Game win = 3, draw = 1, loss = 0.

**Tiebreaker chain (in order):**

1. **Match points** (primary ranking)
2. **Opponents' Match-Win Percentage (OMW%)**
3. **Game-Win Percentage (GW%)**
4. **Opponents' Game-Win Percentage (OGW%)**

**Formulas:**

- Match-Win Percentage (MWP) for any player:
  `MWP = match points earned / (3 × rounds played)`
  — floored at **0.33** if the raw value is lower, to limit how much one very weak opponent can drag down another player's tiebreaker.

- OMW% (a player's own tiebreaker):
  `OMW% = average of MWP across all opponents faced` (byes excluded from the average — a bye is not an "opponent")

- Game-Win Percentage (GW%):
  `GW% = game points earned / (3 × games played)` — same 0.33 floor applies.

- OGW%: average of opponents' GW%, same floor rule.

- **Byes** count as a 2–0 win for match/game point purposes, but the bye itself is excluded when calculating *your opponents'* averages (you don't get penalized for having faced a "bye opponent" with an undefined record).

**Source:** Wizards of the Coast Magic Tournament Rules, Appendix C.

---

## 2. Yu-Gi-Oh! Trading Card Game

**Match structure:** Best-of-3 per round in Swiss and single-elimination.

**Recent rule change (Tournament Policy v2.5, effective Sept 5, 2025):** draws — intentional or otherwise — were removed entirely. An unresolved match at time limit is now a **double loss** for both players, not a draw. Top cut is capped at Top 8 regardless of attendance (previously scaled up to Top 64).

**Tiebreaker system (Konami Tournament Software / KTS):**

Konami's own published documentation is less granular than MTG's Appendix C, but the mechanism described is:

1. **Match points** (primary)
2. A strength-of-schedule figure derived from **your opponents' records**
3. A secondary figure derived from **your opponents' opponents' records**

This is structurally closer to Pokémon's OWP/OOWP resistance system (opponent win % → opponent's-opponent win %) than to MTG's percentage-chain-with-floor. It is *not* confirmed to use the same 0.33 floor or the same percentage-of-max-points formula as MTG — treat this as a **separate tiebreaker shape** in the ruleset module, not a copy of the MTG one with different constants, until the exact public formula is verified.

**Open item:** get the precise KTS formula (floor values, whether game-level stats factor in at all) before implementing — the community-facing documentation describes the mechanism but not the exact arithmetic the way MTG's Appendix C does.

---

## 3. One Piece Card Game

**Match structure — the standout difference:** Swiss/preliminary rounds are **best-of-one** (a single game decides the match), while Top Cut playoff rounds switch to **best-of-three**. This split (Bo1 Swiss → Bo3 elimination) doesn't appear in MTG, Yu-Gi-Oh, or Lorcana, and is a real branch point for the ruleset module — match format isn't constant across the tournament's own phases.

**Draws:** not permitted in single-elimination rounds; if both players simultaneously meet a loss condition, the current turn-player is ruled the loser. In Swiss, an unresolved match at time limit with active/unresolved card effects becomes a double loss.

**Top cut sizing:** scales with attendance — Top 8 for smaller events, Top 16 for larger ones (exact attendance thresholds are tournament-tier dependent — check the current Tournament Rules Manual for the specific cutoffs in effect).

**Tiebreakers:** community tooling (e.g., third-party Swiss calculators) treats One Piece as using an opponent win-rate-style bubble tiebreaker similar to the MTG/Lorcana family, but Bandai's own published Tournament Rules Manual doesn't lay out the exact formula with MTG's level of precision.

**Open item:** confirm the exact One Piece tiebreak formula (floor value if any, whether it's percentage-based or a raw win-count sum) directly from Bandai's Tournament Rules Manual before assuming it's identical to the MTG chain — the *shape* looks similar but constants are unverified.

---

## 4. Disney Lorcana

**Match structure:** Best-of-3, standard Swiss-into-single-elimination Top 8 — structurally the closest of the five to MTG.

**Points:** Match win = 3, draw = 1, loss = 0. Same shape as MTG.

**Tiebreaker chain:** identical shape to MTG —

1. Match points
2. **OMW%** — average of opponents' Match-Win Percentage, each floored at 33%, byes excluded
3. **GW%** — own game-win percentage, floored at 33%
4. **OGW%** — average of opponents' GW%, floored at 33%

**Bye handling:** a bye awards match points as a win, and the bye "opponent" is excluded from OMW% calculations — same neutral-to-positive treatment as MTG.

**Practical note:** if the ruleset module implements MTG's tiebreaker chain as a configurable strategy (point values, floor value, which stats factor in), Lorcana likely needs zero new logic — just the same strategy selected for the Lorcana ruleset. This is the clearest "adopt with near-zero marginal effort" case in this research.

---

## 5. Flesh and Blood

**Match structure — also a standout:** Swiss rounds are **best-of-one**. Top 8 playoff is also **best-of-one**, single-elimination, and untimed (no time limit once in Top 8).

**Draws:** possible in Swiss via the timed-round extra-turn procedure (turn player finishes their turn, one additional turn is played, and if no winner is determined the game is a draw). Explicitly **not** an acceptable result in elimination rounds — a different resolution procedure applies there instead.

**Tiebreaker — structurally different from the other four:**

Primary tiebreaker is **Cumulative Match Points (CMP)**, not an opponent-average percentage. CMP is described as a fractional value between 0 and 1, built from whether the player won *each individual round* over the course of the tournament, weighted toward rounds later in the event — a player who was winning consistently earlier holds a better CMP than someone who won the same total number of matches but caught up late.

This means CMP needs **the player's own round-by-round result history as an ordered sequence**, not just a final aggregate — a fundamentally different data shape than OMW%, which only needs opponents' *final* records.

A secondary tiebreaker, **Match Loss Percentage (MLP)**, favors the player with the fewest average match losses among matches actually played.

**Open item:** get the exact CMP summation formula from Flesh and Blood's official Tournament Rules and Policy / Appendix (the published description confirms the *shape* of the formula — round-indexed, recency-weighted — but the full closed-form expression should be pulled directly from the source doc before implementation, to avoid guessing at the exact weighting).

---

## 6. Architectural implication for the ruleset module

Given the above, the tiebreaker interface should support (at minimum) **two distinct algorithm families**, not one parameterized formula:

**Family A — Opponent-average percentage chain** (MTG, Lorcana, likely Yu-Gi-Oh and One Piece with different constants):
- Input needed: each opponent's *final* match/game record for the event.
- Config per game: point values (win/draw/loss), floor percentage (if any), which stats are included in the chain (e.g., Yu-Gi-Oh may not need a game-level GW%/OGW% step at all if Konami's system only goes two levels deep: own record → opponents' records → opponents' opponents' records).
- If this is built as one configurable strategy, adding Lorcana (and likely Yu-Gi-Oh/One Piece once formulas are confirmed) should require **config only, no new code**.

**Family B — Cumulative/round-history based** (Flesh and Blood; conceptually closer to chess's cumulative Buchholz-style tiebreaks mentioned in earlier research):
- Input needed: the player's own per-round outcome sequence, in order.
- This is a genuinely separate implementation, not a config variant of Family A.

**Practical takeaway for "adopt more TCGs with little effort":** the effort scales with which family a new game uses, not with the game itself. A sixth TCG that uses an OMW%-style chain is near-zero marginal effort once Family A is built generically. A game using a cumulative or Buchholz-style system reuses Family B instead. The risk case is a future game using a *third* fundamentally different tiebreak philosophy (e.g., a pure Sonneborn-Berger opponent-strength-sum, which weights wins over strong opponents more than wins over weak ones, rather than averaging or accumulating) — worth remaining open to a Family C if that comes up, rather than assuming two families cover everything indefinitely.

---

## 7. Open verification items (before hardcoding)

- [ ] Confirm exact Yu-Gi-Oh! KTS tiebreaker formula and floor value (if any) from Konami's current published documentation.
- [ ] Confirm One Piece's exact tiebreak formula and current Top 8 / Top 16 attendance thresholds from Bandai's current Tournament Rules Manual.
- [ ] Pull the full closed-form CMP formula (and MLP formula) from Flesh and Blood's official Tournament Rules and Policy Appendix.
- [ ] Verify whether any of these games' formulas have changed since this research (all TCG tournament policies get periodic version updates — check current version numbers before implementation, not just at research time).
