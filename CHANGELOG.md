# Changelog

All notable changes to this project are documented here, one entry per
MVP tag. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

## [0.1.0] — MVP1: Core In-Person Swiss Engine

Serves BR1-BR4 / FR1-23, FR25-26. Full Build Order: phases 1-9.

### Added

- Repo scaffold (FastAPI + React/TS/Vite), CI, Sphinx docs scaffold (Phase 1)
- Kubernetes staging deployment via Helm + Percona PG Operator (Phase 2)
- Domain model: Event/Pod/Entry/Round/Match, `TournamentFormat` +
  `GameModule` plugin interfaces (Phase 3)
- Swiss pairing/round generation and seating (Phase 4)
- Operational API, RBAC, OIDC auth, published OpenAPI spec (Phase 5)
- Match and tournament reporting: BO1 results with provenance, final
  report (Phase 6)
- Operational UI: setup, pairings/seating, BO1 scoring, final report,
  persona switcher (Phase 7)
- Real Swiss tiebreakers (OMW%/OOMW%) behind a pluggable
  `TiebreakStrategy` interface, replacing the UUID-string stopgap (Phase 8,
  FR25)
- Versioned Sphinx docs site: data-model reference (autodoc), API usage
  guide, deployment guide; served by a new Helm-managed `docs` component
  (Phase 9, FR23)

### Known follow-ups (not blocking, tracked as issues)

- #57 — tiebreak API/UI wire contract has no label/strategy identifier;
  needed before a second `TiebreakStrategy` family ships under #41.
