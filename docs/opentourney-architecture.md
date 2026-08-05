# OpenTourney — Core Engine Architecture

Reference doc describing the tournament lifecycle as a set of distinct engines, and how the previously documented enhancements and ruleset research map onto them. Companion docs: `opentourney-enhancements.md`, `tcg-ruleset-research.md`.

---

## 1. Lifecycle overview

```
Organizer creates tournament (selects game/ruleset)
        |
Players sign up
        |
   [ SWISS PHASE ]
        |
        v
Pairing Engine: pair round N  <-------------------+
        |                                          |
Players play matches                               |
        |                                          |
Reporting Engine: results submitted / confirmed /   |
                  deconflicted (dual submission +   |
                  judge override)                   |
        |                                          |
Organizer concludes round (hard gate — see 3.3)     |
        |                                          |
Stats Engine: recompute standings, tiebreakers ----+
        |
   (repeat until Swiss rounds complete)
        |
        v
   [ CUTOFF / SEEDING ]
        |
Stats Engine: final Swiss standings -> seed Top Cut
        |
        v
   [ PLAYOFF PHASE ]
        |
        v
Pairing Engine (bracket mode): seeded bracket pairing <---+
        |                                                   |
Players play matches                                        |
        |                                                    |
Reporting Engine (playoff rules — often no draws,            |
                  different timeout resolution)              |
        |                                                    |
Stats Engine: bracket advancement --------------------------+
        |
   (repeat until final)
        |
        v
Organizer concludes tournament
        |
Stats Engine: final standings, winner determination
        |
Results reported / exported
```

**Key structural point:** this is a loop within two phases, not a single pipeline. The Pairing Engine and Stats Engine are each invoked once per round, and each round's Stats Engine output is the next round's Pairing Engine input. Swiss and Playoff are separate phases with different pairing strategies and different reporting rules — not one continuous mode.

---

## 2. The four engines

### 2.1 Pairing Engine

**Responsibility:** given current standings and match history, produce the next round's pairings.

**Two distinct modes, not one:**
- **Swiss mode** — pairs players with equal/similar records, avoids rematches (or allows them only past a ruleset-defined round threshold), handles byes for odd player counts.
- **Bracket/playoff mode** — seeded single- or double-elimination pairing based on final Swiss standings. Different logic entirely; no "avoid rematch" concerns, no score-based pairing.

**Ruleset-specific inputs it needs:**
- Match format per phase (e.g., One Piece: Bo1 in Swiss, Bo3 in Top Cut — the Pairing Engine needs to know which format applies to the round it's generating, not assume one format for the whole tournament).
- Pairing constraints (rematch avoidance rules, color/seat balancing if relevant — chess-style constraints if that module is ever built).

**Depends on:** Stats Engine output from the prior round (standings must be settled before pairing runs — see 3.3 gate).

### 2.2 Reporting Engine

**Responsibility:** collect and reconcile match results from `unreported` to a final, trusted `result`.

**Covers the previously-documented dual-submission + deconfliction workflow:**
- Player A / Player B self-report via mobile.
- Matching reports auto-confirm.
- Mismatched reports (or one-sided non-submission) escalate to deconfliction — timer-based dashboard, floor judge check, organizer resolution if needed.
- Judge report acts as a third reporter role with override authority (see enhancements doc §2 for the schema this maps to — `reports` list distinct from final `result`/`reported_by`, `witnessed_by` reserved for staff confirmation).

**Ruleset-specific variation:**
- Whether draws are a legal outcome at all (MTG/Lorcana/FaB Swiss: yes; Yu-Gi-Oh/One Piece: no, unresolved → double loss).
- Playoff-phase rules often differ from Swiss-phase rules for the *same* game (e.g., FaB and One Piece both disallow draws in elimination rounds even though Swiss allows them) — the Reporting Engine needs to know which phase a match belongs to, not just which game.

**Feeds into:** Stats Engine (only once a match's result is finalized — a match sitting in `awaiting_second_report` or `disputed` should not be readable by the Stats Engine as a completed result).

### 2.3 Stats Engine

**Responsibility:** given a full set of finalized round results, compute updated standings — match points, tiebreakers, and (in playoff phase) bracket advancement.

**This is the module most directly shaped by `tcg-ruleset-research.md`.** Two algorithm families identified there:

- **Family A — opponent-average percentage chain** (MTG, Lorcana, likely Yu-Gi-Oh/One Piece pending formula confirmation): needs each opponent's *final* record as input. Configurable via point values, floor percentage, and chain depth (how many levels of averaging).
- **Family B — cumulative/round-history based** (Flesh and Blood's CMP): needs the *player's own* per-round outcome sequence, in order, not just opponents' final records. Structurally separate implementation, not a config variant of Family A.

**Design implication:** the Stats Engine's interface must support both input shapes — "give me opponents' final records" and "give me my own round-by-round history" — since a single input contract modeled only on Family A would make Family B impossible to implement without reworking the interface later.

**Playoff-phase behavior differs from Swiss-phase behavior:** in Swiss, the Stats Engine recomputes full standings every round. In playoff/bracket mode, its job shrinks to "who won, who advances" — no tiebreakers needed in single-elimination (a loss just eliminates you), though double-elimination or Swiss-into-Top-16-with-partial-losses (One Piece's Top 16 qualification by opponent win rate) still needs tiebreaker logic even at the cutoff boundary.

### 2.4 (Implicit) Phase/Transition Engine

Not called out explicitly in the original flow, but worth naming: something has to own the **Swiss → Cutoff → Playoff** transition — deciding when Swiss rounds end (fixed round count vs. Bandai's "variable rounds until one undefeated player" model), computing the cutoff (Top 8 vs Top 16 by attendance), and switching the active Pairing Engine mode and Reporting Engine ruleset from Swiss to Playoff.

This may not need to be a fourth "engine" in the codebase, but it is a distinct **responsibility** — likely owned by the tournament's phase/state field plus a transition function, rather than living inside the Pairing or Stats engines themselves. Flagging it now so it doesn't get silently absorbed into one of the other three and become tangled logic later.

---

## 3. Cross-cutting design notes

### 3.1 Ruleset module owns per-phase configuration, not just per-game configuration

Earlier design assumed a ruleset module (e.g., "Pokémon," "MTG") configures the three engines once. The research shows several games need **per-phase** configuration within a single ruleset:
- Match format (Bo1 vs Bo3) can differ between Swiss and Playoff (One Piece, and FaB's Swiss-Bo1/Playoff-Bo1-but-untimed).
- Draw legality can differ between Swiss and Playoff (FaB, One Piece).

**Implication:** a ruleset module's config shape should be `{ swiss: {...}, playoff: {...} }` at minimum, not a single flat config applied uniformly across the whole tournament.

### 3.2 Reporting Engine and Stats Engine share the audit-trail requirement

The `confirmed_by` / `reports` list structure from the enhancements doc isn't just for dispute resolution — it's also the Stats Engine's source of truth for "was this result actually finalized." A round shouldn't be closable (3.3) if any match lacks a finalized report chain.

### 3.3 Organizer "conclude round" must be a hard gate, not just a button

Raised in conversation and worth capturing formally: concluding a round should be blocked if any match in that round is `unreported`, `awaiting_second_report`, or `disputed`. Allowing a round to close with unresolved matches would let the Pairing Engine generate the next round's pairings off incomplete standings — silently wrong pairings that are hard to detect after the fact.

### 3.4 Bracket/elimination phase reuses the Reporting Engine, not a separate one

Worth being explicit that the Playoff phase doesn't need its own reporting mechanism — same dual-submission/judge-override flow applies, just with different ruleset config (draws off, different timeout resolution). Avoids duplicating the reporting workflow per phase.

---

## 4. Open questions carried forward

- [ ] Does the Phase/Transition responsibility (2.4) need to be a first-class service, or is it sufficiently handled as tournament state + a transition function? Revisit once the Pokémon module is far enough along to test against a real "Swiss ends, Top Cut begins" transition.
- [ ] For games with variable-round-count Swiss (announced criteria rather than fixed rounds, per Bandai's example in the One Piece Tournament Rules Manual), how does the Pairing Engine know a round is the *last* Swiss round before it's played? Likely needs a per-round check against the ruleset's ending criteria, run by the Phase/Transition responsibility before the Pairing Engine is invoked for what might be a Swiss or might be a Cutoff round.
- [ ] Confirm whether any currently-scoped game needs double-elimination in the Playoff phase (referenced historically for MTG in some formats) — if so, Pairing Engine's bracket mode needs to support both single- and double-elimination topologies, not just single.
