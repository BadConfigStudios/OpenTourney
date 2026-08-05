# OpenTourney — Enhancements & Design Notes

Working doc for features discussed during planning, captured 2026-08-05.
Organized by area, roughly in priority order within each section. Most
sections have been filed as GitHub issues (linked below); Sections 7 and 8
are directional notes / open questions, not yet actionable.

---

## 1. Core Architecture — Ruleset Modularity

**Issue: Define ruleset module interface (match schema, tiebreaks, pairing)**

Split "ruleset" into three independently pluggable concerns so game modules
(Pokémon, MTG, future TCGs) don't leak into each other or into the core
engine:

1. **Match outcome schema & scoring**
   - Model outcomes as `{ result: win | loss | draw, score: number }` per
     player from day one, even though Pokémon v1 will only populate
     win/loss.
   - Cheap to include now; expensive to retrofit once standings tables and
     the pairing engine assume binary outcomes.
2. **Tiebreak calculation**
   - Interface shape: `calculateTiebreak(matchHistory, roundResults) ->
     score | scoreChain`
   - Don't assume a single-number output — some systems (chain tiebreaks)
     need ordered lists of tiebreak criteria (primary, secondary,
     tertiary), not one score.
   - Pokémon: OWP / OOMW (resistance-style, percentage-based).
   - Chess (if ever pursued): Buchholz, Sonneborn-Berger (opponent-strength
     sums, not percentages).
3. **Pairing algorithm / constraints**
   - Keep pluggable per ruleset. TCG Swiss implementations are typically
     looser about repeat pairings than chess's Dutch-system rules — don't
     assume one pairing engine covers every game fairly.

**Acceptance criteria:** Adding a second TCG module requires no changes to
the core pairing/bracket engine — only a new ruleset module implementing
the three interfaces above.

---

## 2. Match Result Reporting Model

**Issue: Design multi-reporter match result schema**

- Store results as a list of reports, not two fixed fields:
  `reports: [{ reporter_id, role, result, timestamp }]`
- Roles: `player_a`, `player_b`, `judge` (future).
- Judge submissions should be modeled as an **override**, not just a
  tiebreaker — a judge report can supersede two *matching* player reports
  if something was observed to be wrong (rules infraction, misreported
  result), not only used to break a disagreement.
- Preserve full audit trail: original player submissions + any override +
  who overrode + when. Needed for dispute resolution and organizer trust
  in competitive/cash events.

**Why now:** Retrofitting a reporter-role system after result entry is
built as two hardcoded fields is a real rework. Cheap to build correctly
from v1.

(Related: a minimal single-reporter version of this — a `method` field on
`Match` — shipped in Phase 7 PR3; this issue tracks the fuller
dual-submission/override model. See DECISIONS.md 2026-08-05 and issue #40.)

---

## 3. Mobile Pairing & Self-Reporting (In-Person Events)

**Issue: Player-facing pairing view (read-only)**

- Players see their round pairing, table number, and current standing on
  their phone. No paper/projector dependency.
- Ship this before self-reporting — lowest risk, highest immediate value,
  and differentiates from both LimitlessTCG and TOM (neither has a
  player-facing mobile UI).

**Issue: Dual-confirmation result submission**

- Both players submit their claimed result from the app.
- Matching submissions auto-confirm the result.
- Mismatched submissions flag for deconfliction (see Section 4).

**Issue: No-show / non-submission policy**

- If a player has not submitted a result **and** does not appear when
  called for deconfliction, treat as a drop for that round (auto-loss to
  opponent), per organizer's discretion on wording ("forfeit this round"
  vs. full tournament drop — pick one and be explicit in rules text, since
  "drop" implies full withdrawal in TCG contexts).
- Must be stated to players **before the event** (check-in materials /
  in-app rules), not discovered for the first time when enforced.
- Do not let this be a pure app/timer-only ruling — require a human check
  (floor judge at the table, or staff call-out) before finalizing, to rule
  out phone/notification failure vs. genuine absence.

---

## 4. Deconfliction Workflow

**Issue: Deconfliction dashboard (organizer-facing, v1)**

- Trigger: first player submission starts a visible timer on that match.
- Escalation tiers (suggested, tune later):
  - T1 (short, ~2–3 min): table surfaces on dashboard as "awaiting second
    submission."
  - T2: table flagged for floor check.
- Dashboard status model per flagged table (minimum fields):
  - Table number, time since first submission, judge assigned (y/n),
    judge check-in status, judge's on-site read (`still playing` / `done,
    forgot to submit` / `one player absent` / `active dispute`).
- Sort/highlight by longest-waiting first so staff can triage during busy
  rounds.

**Issue: Organizer resolution screen**

- When escalated to organizer, screen should pre-populate: both original
  submissions, judge's on-site notes (if any), table number, round time
  remaining.
- Organizer should not have to re-interview players from scratch — the
  point of floor-judge involvement is to shorten this step.

**Future / Phase 2 — not blocking v1:**

**Issue: Floor judge dashboard + assigned table groups**
- Judges get their own dashboard scoped to an assigned set of tables.
- Judge can submit a third report type (`match concluded`) — treated as
  the override role described in Section 2.
- Open design question: do judges get standalone ruling authority for
  clear-cut cases (e.g., confirmed absence → forfeit), or does everything
  funnel to the organizer? Leaning toward giving judges authority on
  clear-cut absence/forfeit calls, escalating only genuine disputes —
  avoids single-organizer bottleneck at larger events.
- This implies a staff-permissions/role model (organizer > judge > table
  scope). Treat as a separate scoped project — don't build speculatively
  before real organizer usage data shows it's needed.

---

## 5. Multi-Game Ruleset Modules

**Issue: Pokémon TCG ruleset module (v1 launch)**

- OWP/OOMW tiebreaks, Swiss + single/double elimination, decklist-adjacent
  metadata.

**Issue: MTG ruleset module (module 2)**

- Validate the module abstraction from Section 1 against a second real
  game before committing further.
- Considerations: best-of-1 vs best-of-3, multiplayer/Commander pod
  support, format-specific deck-legality metadata.

**Deferred / not currently planned:**
- Chess module — deprioritized due to FIDE/USCF certification requirements
  for rated play (Dutch-system pairing compliance, TRFX export format)
  being a compliance project, not a coding task. Revisit only if pursuing
  certification directly, or scope explicitly as casual/unrated-only.

---

## 6. Onboarding & Access Model

**Issue: Self-serve organization creation (no manual approval)**

- Core differentiator vs. LimitlessTCG's manual review queue.
- Same-day: create org → host tournament, no application/waiting period.

**Issue: Lightweight automated trust/abuse controls**

- Since there's no manual approval gate, add automated signals to catch
  abuse without reintroducing approval friction:
  - New-org rate limiting.
  - Verified email/domain.
  - Delay prize/payout-related features until an org has run a few clean
    events.
- Goal: same-day onboarding without becoming known for spam/scam
  tournaments.

---

## 7. Tiering / Monetization (directional notes, not final)

- Avoid gating the free/shared tier primarily on **player count** —
  doesn't track actual infra cost (Swiss/bracket engines are lightweight)
  and risks losing users to LimitlessTCG's uncapped free tier before they
  see OpenTourney's actual differentiators.
- Prefer gating on:
  - Tournament frequency/volume per month (shared infra).
  - API / pods access (programmatic access, webhooks, custom pod configs)
    — paid unlock, since this has no equivalent on LimitlessTCG.
  - Isolated K8s instance as its own tier — dedicated infra, custom
    domain, SLA, support, independent of player count.
- Softer free-tier gates to consider: branding/watermark, results
  retention window, number of staff/organizer seats.

---

## 8. Open Questions / Not Yet Decided

- [ ] Judge ruling authority scope (clear-cut cases only vs. everything to
      organizer).
- [ ] Exact wording/policy for round-forfeit vs. full-tournament-drop on
      no-show.
- [ ] Non-app fallback for deconfliction calls (audio call-out, staff
      walk-by) to avoid pure-notification-failure false drops.
- [ ] Round timer model: organizer-driven "call time" vs. hard automatic
      timer.
- [ ] MTG module launch timing relative to Pokémon v1 stabilization.
