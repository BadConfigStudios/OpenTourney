# Requirements & MVP Traceability

Tracks Business Requirements (BR), Functional Requirements (FR), and
Non-Functional Requirements (NFR) for OpenTourney, mapped to the MVPs and
phases that implement them. See `README.md` for the full design rationale
behind each decision reflected here.

## Business Requirements (BR)

- **BR1**: Enable an organizer to run a real in-person tournament event
  end-to-end (setup, pairings, scoring, standings/reporting) without
  depending on any third-party platform's approval process.
- **BR2**: Provide a genuinely open, game-agnostic standard — a published
  API and data schema — so any host application, in any language, can
  integrate as a client without OpenTourney assuming its auth, UI, or
  data model.
- **BR3**: Keep tournament-operational data (PII-adjacent: player
  references, match-level results) separated from any future public
  meta/analytics surface by construction, not by convention or filtering.
- **BR4**: Design for modularity — pluggable tournament formats and
  pluggable game-specific metadata — so new formats and games are
  drop-in additions, not core rewrites.

## Functional Requirements (FR) — MVP1

| ID | Requirement | Serves | Phase |
|----|-------------|--------|-------|
| FR1 | FastAPI backend skeleton with `/healthz` | BR1 | 1 |
| FR2 | React + TypeScript + Vite frontend skeleton | BR1 | 1 |
| FR3 | CI via GitHub Actions on `badconfig-runners` (backend + frontend build/test) | BR1 | 1 |
| FR4 | Sphinx docs scaffold, builds cleanly in CI | BR2 | 1 |
| FR5 | Helm chart (backend + frontend Deployments/Services, Percona PG Operator) deployable to k3s staging namespace | BR1 | 2 |
| FR6 | CD workflow building/pushing images via `badconfig-runners` | BR1 | 2 |
| FR7 | `Event` model: date, in-person only for v1 | BR1, BR4 | 3 |
| FR8 | `Pod` model: schema supports many per event; v1 API/UI constrains to exactly one per event | BR1, BR4 | 3 |
| FR9 | `Entry` model (player reference + generic metadata), `Round`, `Match` (BO1) | BR1, BR4 | 3 |
| FR10 | `TournamentFormat` plugin interface + Swiss implementation (full per-round loop, pairings depend on prior results) | BR4 | 4 |
| FR11 | Table/seat assignment for in-person pairings | BR1 | 4 |
| FR12 | `GameModule` plugin interface + generic/fallback implementation (no game-specific metadata validation) | BR4 | 3, 5 |
| FR13 | Operational API: CRUD for events/pods/entries (Organizer-driven only; no self-registration in v1) | BR1 | 5 |
| FR14 | OIDC-based authentication: OpenTourney trusts an externally-issued identity assertion, owns no accounts/passwords | BR2 | 5 |
| FR15 | RBAC: Organizer/Scorekeeper/User roles, scoped per event/pod, enforced on all operational endpoints | BR1, BR3 | 5 |
| FR16 | Published, versioned OpenAPI spec, auto-generated and kept current with the implementation | BR2 | 5 |
| FR17 | Match result reporting: BO1 result + `reported_by`/`witnessed_by`/`confirmed_by` provenance | BR1, BR3 | 6 |
| FR18 | Tournament-completion detection (all rounds done) + final standings/placement report | BR1 | 6 |
| FR19 | Operational UI: event/pod/entry setup | BR1 | 7 |
| FR20 | Operational UI: Swiss pairings + seating display | BR1 | 7 |
| FR21 | Operational UI: BO1 scoring, gated by RBAC role | BR1 | 7 |
| FR22 | Operational UI: final report display | BR1 | 7 |
| FR23 | Sphinx docs content: data-model reference (autodoc), API usage guide, deployment guide — versioned per release | BR2 | 8 |

## Non-Functional Requirements (NFR)

| ID | Requirement |
|----|-------------|
| NFR1 | TDD (red→green→refactor) for all code |
| NFR2 | API-first: the reference UI has no private/backend-only access beyond the published API (see README) |
| NFR3 | Every phase verified against the real Kubernetes staging environment, not deferred to a final integration phase |
| NFR4 | OpenTourney owns no accounts or passwords; authentication is always externally asserted |
| NFR5 | `TournamentFormat` and `GameModule` plugin interfaces stay fully decoupled — neither assumes anything about the other |

## MVP Breakdown

### MVP1 — Core In-Person Swiss Engine (target `v0.1.0`)

Serves BR1–BR4 / FR1–FR23. Phases 1–8.

**Acceptance**: An Organizer can authenticate (OIDC), create an in-person
Event with one Pod (Swiss format, generic game module), add Entries, and
run the event through the operational UI — Round 1 pairings with seating,
Scorekeeper/Organizer-entered BO1 results with provenance, subsequent
rounds generated from standings, through to a final standings/placement
report — entirely via the published, versioned API, deployed and verified
on the Kubernetes staging environment, with Sphinx docs covering the data
model, API usage, and deployment.

**Deferred to future MVPs** (core scope, sequenced later, not
architectural non-goals): Pokémon TCG (and other) `GameModule`s,
single/double-elimination and multi-phase `TournamentFormat`s, BO3,
self-service player registration, online modality (per-game module:
username discovery, friending instructions, match setup).

**Roadmap** (auxiliary/integration work, see README): SAML/LDAP auth,
embeddable UI module, presentation mode, public meta/analytics API,
federation/cross-instance analysis.

## Build Order

| Phase | Description | MVP |
|-------|-------------|-----|
| 1 | Repo scaffold + CI (FastAPI + React/TS/Vite skeletons, `/healthz`, Dockerfiles, `badconfig-runners` CI, Sphinx scaffold) | MVP1 |
| 2 | Kubernetes staging deployment (Helm chart, Percona PG Operator, CD via `badconfig-runners`, staging deploy docs) | MVP1 |
| 3 | Domain model (Event/Pod/Entry/Round/Match, `TournamentFormat` + `GameModule` interfaces, Swiss-only + generic-only for v1) | MVP1 |
| 4 | Swiss pairing/round generation + seating | MVP1 |
| 5 | Operational API + RBAC + OIDC + published OpenAPI spec | MVP1 |
| 6 | Match & tournament reporting (BO1 + provenance + final report) | MVP1 |
| 7 | Operational UI (setup, pairings, scoring, final report) | MVP1 |
| 8 | MVP1 verification (full suite, staging verification, versioned docs site, release cut `v0.1.0`) | MVP1 |
