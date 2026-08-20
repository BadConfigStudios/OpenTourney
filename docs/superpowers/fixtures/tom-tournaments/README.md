# TOM Cross-Validation Fixtures

Real Tournament Operations Manager (TOM) XML exports, used to cross-validate
`PokemonTiebreak`'s output against ground-truth tournament results (Phase 18,
FR28/FR29). See `docs/superpowers/specs/2026-08-20-phase18-pokemon-tiebreak-headtohead-design.md`
section 5 for how these are used.

Only the final-state export of each tournament is kept (`<standings>` and all
completed `<rounds>` present) — the intermediate per-round snapshots supplied
during design aren't needed for the test harness.

- `cg-league-night-2026-07-28.xml` — 16→14 players, 3 rounds, age-combined
  pairing (categories 0/1/2), no bye, 2 drops (one 0-1, one 1-0), one genuine
  tie (round 2, table 4, `outcome="3"`). Use the 12-player category "2"
  (Masters) subset — validates the tie-numerator open item.
- `round-rock-summer-2026-06-20.xml` — pod `category="0"`, 23→18 players
  (self-contained, not age-combined with the tournament's other pod), 3
  rounds, 1 bye (round 1, `outcome="5"`, single-`<player>` match), 5 drops
  after round 1. Primary fixture — covers bye-denominator handling, the
  25%/75%/100% floor-and-cap, and real final ranking order end to end.

## TOM XML notes (relevant to the fixture parser)

- `outcome="1"` = player1 win, `outcome="2"` = player2 win, `outcome="3"` = tie,
  `outcome="5"` = bye (match has a single `<player>`, not `<player1>`/`<player2>`),
  `outcome="0"` = unplayed/pending (only appears in mid-round snapshots, never
  in a final export — ignore if encountered).
- `<player>` elements carry `<dropped><round>N</round></dropped>` when a
  competitor dropped after round N.
- `<standings>` exports final **rank/place only** — no computed Op Win%/Op Op
  Win%/Op Op values. Cross-validation compares final rank order, not
  intermediate percentages (those are hand-derived from the handbook formula
  as a secondary check, not diffed against TOM directly since TOM doesn't
  export them).
