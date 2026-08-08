# Technical Decisions

Log of non-trivial technical decisions, with rationale. See `README.md`
for full design context and `REQUIREMENTS.md` for how these map to
phases.

## 2026-07-19 — Backend stack: Python + FastAPI

Matches limitless-organizer-tracker and club-checkin. Reuses their proven
Helm/Fleet deployment pattern directly, and FastAPI auto-generates an
OpenAPI spec, which fits the API-first requirement (published, versioned
spec kept current with the implementation) with minimal extra effort.

## 2026-07-19 — Frontend stack: React + TypeScript + Vite + TanStack Query

Matches limitless-organizer-tracker's exact pattern — proven tooling,
TanStack Query handles server state cleanly against a REST API, and
conventions carry over directly from an existing, working codebase.

## 2026-07-19 — Docs toolchain: Sphinx

Python-native; autodoc pulls documentation directly from FastAPI/Pydantic
models, so data-model docs can't silently drift from the code the way
hand-written docs can. `sphinx-multiversion` handles per-version docs,
matching the requirement to document each release.

## 2026-07-19 — Kubernetes staging environment and CI from day one

Unlike limitless-organizer-tracker and club-checkin, which added
Helm/Fleet staging deployment several phases in, OpenTourney stands up
the k3s staging environment and `badconfig-runners`-based CI/CD in
Phases 1–2. Every subsequent phase is verified against real staging
infrastructure rather than Docker Compose alone, catching integration
issues earlier.

## 2026-07-19 — Authentication: externally-asserted identity only

OpenTourney owns no accounts, login, or passwords. It trusts an identity
assertion issued by whatever host system authenticated the caller, and
never re-implements authentication itself. v1 ships OIDC only; SAML and
LDAP-backed support are staged as separate roadmap items. This keeps
OpenTourney's own scope minimal and lets any host's existing identity
infrastructure integrate directly, which is necessary for it to function
as an open standard rather than a library tied to one host's auth stack.

## 2026-07-19 — Authorization: OpenTourney owns RBAC, scoped per event/pod

Even though authentication is delegated, authorization is not: OpenTourney
maps each authenticated identity to a role (Organizer, Scorekeeper,
User/Player) scoped per event/pod. This is what makes match-result
provenance (`witnessed_by`, `confirmed_by`) enforceable rather than
self-declared — a `witnessed_by` value only means something if OpenTourney
can verify the witness genuinely holds the Scorekeeper role for that pod.

## 2026-07-19 — `Pod` kept in schema, cardinality constrained in v1

`Pod` remains a real entity supporting many-per-event, but v1's API/UI
constrains events to exactly one pod. This avoids a schema migration when
multi-pod (e.g. age divisions) returns in a later MVP — re-enabling it is
relaxing a validation rule, not restructuring the domain model.

## 2026-07-19 — Online modality excluded from MVP1 entirely

Online tournament support isn't a simple flag — it requires a genuinely
separate, per-game subsystem (in-game username discovery, friending
instructions, match setup instructions, all differing by game). Rather
than add a half-built `modality` field to `Event`, v1 is in-person only;
online support is deferred to a future MVP as a per-game module once it's
actually being designed.

## 2026-07-19 — Two independent plugin systems: `TournamentFormat` and `GameModule`

- `TournamentFormat` — how rounds/pairings work (Swiss, single-elim,
  double-elim, multi-phase). MVP1 implements Swiss only.
- `GameModule` — what "what they're playing" means per game (Pokémon
  TCG's decklist validation, Chess needing nothing extra, etc.). MVP1
  implements a generic/fallback module only — deliberately no Pokémon TCG
  module yet (see below).

These two interfaces are kept fully decoupled: neither assumes anything
about the other, so a host (e.g. club-checkin) can pick any format for a
game with no dedicated `GameModule`, and vice versa.

## 2026-07-19 — MVP1 ships generic-only `GameModule`, no Pokémon TCG module

Shipping a real game module (e.g. Pokémon TCG's decklist validation)
alongside the interface it's meant to test doesn't actually prove the
abstraction is clean — it's easy for coupling to hide when both are built
together. Shipping generic-only in MVP1, then adding Pokémon TCG as a
genuine drop-in module in a later MVP, is the real test of whether the
plugin architecture holds up. It also keeps MVP1's Phase 3/5 scope smaller
(no decklist-shaped validation to build yet).

## 2026-08-01 — Data-access: SQLAlchemy 2.0 + Alembic

Phase 3 introduces the first DB-backed models (`Event`/`Pod`/`Entry`/
`Round`/`Match`). SQLAlchemy 2.0 declarative models pair directly with
Alembic's autogenerate (already named in issue #3's acceptance criteria),
avoiding hand-written migration diffs. Standard, mature choice for
FastAPI + Postgres; matches limitless-organizer-tracker/club-checkin
tooling maturity even though this repo's stack diverges elsewhere.

## 2026-08-01 — Integration-test DB: testcontainers-python

Phase 3's integration tests need a real Postgres, not a mock (per NFR1/TDD
conventions — integration layers use real/containerized deps). `badconfig-
runners` confirmed has a docker daemon (see `ci.yml`'s `docker-build` job).
testcontainers-python spins an ephemeral Postgres per test run via the
docker socket, giving identical behavior locally and in CI with no
workflow-level service-container config to keep in sync — chosen over a
GitHub Actions `services:` Postgres, which would require local devs to
separately run their own matching Postgres (e.g. docker-compose).

## 2026-07-19 — MVP1 scope: BO1 only, Organizer-driven registration only

Best-of-three and self-service player registration are both deferred to
future MVPs, to keep MVP1's Match model and RBAC-gated entry-creation flow
simple. Neither blocks running a real event — an Organizer/Scorekeeper can
still register players manually at check-in.

## 2026-08-02 — `Round.matches` ORM relationship, not an interface signature change

`TournamentFormat.generate_round(entries, previous_rounds)` needs prior
match results to compute standings, but `Round` had no relationship to
`Match` (Phase 3 didn't need one). Rather than change the already-merged
interface signature to carry results explicitly, Phase 4 adds a standard
SQLAlchemy `relationship()` from `Round` to `Match` (the FK already exists
on `Match.round_id`). `previous_rounds: Sequence[Round]` stays exactly as
documented; Swiss reads `round.matches`. No migration needed — additive,
ORM-only change.

## 2026-08-02 — Table/seat assignment: `table_number` on `Match`/`Pairing`, not a separate entity

FR11 only requires a table/seat number attached to each in-person pairing.
Adding `table_number: int | None` directly to `Match` (migration `0005`)
and to the `Pairing` dataclass in `app.formats.base` matches the existing
one-pairing-per-match shape. A separate `Seat`/`Table` entity would add
schema complexity (multi-entry tables, table metadata) that nothing in
v1 scope requires.

## 2026-08-02 — OIDC token validation: PyJWT + `PyJWKClient`

Phase 5 is the first phase validating externally-issued identity assertions.
`PyJWT` (with the `crypto` extra) plus its built-in `PyJWKClient` handles
JWKS fetch/caching and signature verification with a minimal, actively
maintained dependency. `python-jose` was rejected (maintenance has slowed,
past CVEs in its crypto backend); `Authlib` was rejected as broader than
needed — OpenTourney is only ever a Relying Party validating tokens, never
performing OAuth/OIDC flows itself.

## 2026-08-02 — RBAC schema: two explicit tables, not one nullable-scope table

`event_organizers(event_id, player_uuid, source_system)` and
`pod_roles(pod_id, player_uuid, source_system, role)` (role: `scorekeeper` |
`user`) replace a single `role_assignments` table with nullable `event_id`/
`pod_id` columns. Each table's meaning is unambiguous from its columns
alone — no row requires knowing which scope column is null to interpret
what it grants. Organizer is inherently event-wide (manages an event's pods
and entries), so it never needs pod-level granularity; Scorekeeper/User are
inherently pod-scoped.

## 2026-08-02 — Organizer bootstrap: trust an `organizer` claim in the OIDC token

`event_organizers` has no row for a not-yet-created event, so something
else must gate `POST /events`. Rather than add an OpenTourney-owned global
"platform organizer" table (an operator-managed allowlist with no admin UI
in v1), `POST /events` requires the caller's identity assertion to carry an
organizer claim (e.g. `roles: ["organizer"]`) asserted by the host system.
On success, the creator is auto-inserted into `event_organizers` for the new
event. This keeps the claim minimal (identity + host-asserted capability)
and consistent with "OpenTourney owns no accounts" — the host already knows
who its organizers are; OpenTourney still owns all *per-event/pod* RBAC from
that point forward.

## 2026-08-02 — Auth tests: ephemeral keypair + monkeypatched JWKS, never a bypassed dependency

Tests generate a real RSA keypair per session, mint tokens signed with it,
and monkeypatch only the JWKS-fetch step (via `OIDC_JWKS_STATIC` / a
`get_settings` override) to serve that key's public JWK. `decode_token` and
`identity_from_claims` run for real in every test. Rejected: overriding the
`get_current_identity` FastAPI dependency to inject a fake identity directly
— that would mean the validation logic is never actually exercised by any
test.

## 2026-08-02 — Staging OIDC verification: static JWKS env-var escape hatch, no mock IdP

No real external OIDC IdP exists yet for the cube cluster. Rather than
deploy and maintain a mock IdP (e.g. Dex) purely to verify Phase 5, the app
supports `OIDC_JWKS_STATIC` (a fixed JWK set given directly via env/secret,
no HTTP fetch) alongside the production path `OIDC_JWKS_URL` (real
discovery). Staging's Helm values point `OIDC_JWKS_STATIC` at a fixed test
keypair's public JWK; the same private key mints a token locally
(`scripts/mint_test_token.py`) for manual `curl` verification against the
deployed service. When a real host IdP is integrated later, staging simply
switches to `OIDC_JWKS_URL` — no code change.

## 2026-08-02 — Phase 5 split into 4 sequenced PRs

Phase 5 spans DB/auth plumbing, RBAC tables, three CRUD routers, GameModule
wiring, OpenAPI publish, and Helm/staging config — too large for the usual
single-PR/~300-line guardrail. Split as: **PR1** DB session + OIDC/JWT
validation + RBAC tables (no routes yet); **PR2** Events + Pods CRUD
routers; **PR3** Entries CRUD + GameModule wiring + pod-role-assignment
endpoints; **PR4** OpenAPI export/CI drift-check + Helm/staging wiring +
manual verification. Issue #5 stays open across all four, closed after PR4.

## 2026-08-02 — Issues #16/#17 (PR1 deferred findings) slotted into PR4, ahead of the OpenAPI/Helm tasks

PR1's final whole-branch review deferred two items rather than fixing them
inline: issue #16 (Minor — auth/RBAC test-coverage and polish gaps) and
issue #17 (Important — move `Settings`/`JWKSProvider` construction to a
FastAPI startup `lifespan` so misconfiguration fails at boot instead of on
first request). Both are now Tasks 13–14 of PR4's plan, running *before*
the OpenAPI export/Helm/staging-verification tasks (renumbered 15–19),
since issue #17 changes how `app/main.py` constructs the app (every later
PR4 task touching `app/main.py` needs to build on top of the `lifespan`
wrapper, not before it) and issue #16 touches shared test infrastructure
(`tests/support/`) that's cheaper to land before the staging-verification
pass than after.

## 2026-08-02 — `game_slug` validated at Entry creation, not Pod creation

`Pod.game_slug`/`format_slug` are unvalidated free text at write time —
`POST /pods`/`PATCH /pods/{id}` accept any string, deliberately not
importing `app.games.registry` (a later PR3 module). The only place a
`game_slug` is actually dereferenced is `POST/PATCH /entries`, via
`app.games.registry.get_game_module`, which raises `ValueError` for an
unknown slug. PR2's final review caught that the plan's own Task 11 code
called `get_game_module(pod.game_slug)` *outside* its `try/except
ValueError` block — an unrecognized slug would 500, not 422. Fixed in the
plan (both `create_entry` and `update_entry` now wrap the lookup itself,
not just `validate_entry_metadata`), plus a regression test
(`test_entry_creation_rejects_unknown_game_slug_with_422_not_500`).
Deliberately not validating at Pod-creation time instead: that would pull
Task 10's registry into PR2's scope, and Entry creation is where FR12
("`GameModule` wired into Entry creation/validation") already puts the
authoritative check.

## 2026-08-02 — Swiss scoring: 3/1/0 match points, byes count as a win

Standard Play!-style Swiss scoring (win = 3, tie = 1, loss = 0; a bye
scores as a win) drives standings for round 2+. Round 1 pairs entries in
the order passed to `generate_round` (sequential adjacent pairing,
odd-one-out gets the bye) rather than randomizing internally — any
randomization is the caller's responsibility (e.g. shuffling `entries`
before calling), keeping the format itself deterministic and easy to
test.

## 2026-08-03 — MVP1 auth: pre-minted persona tokens + a UI persona switcher, real SSO deferred

MVP1 will run only on the owner's own private cluster, not public-facing;
even if it were externally reachable, the owner accepts blowing the data
away rather than treating it as production. Given that, MVP1 does not
integrate a real IdP (Google or otherwise). Instead:

- The Phase 5 static-JWKS escape hatch (`OIDC_JWKS_STATIC` +
  `scripts/mint_test_token.py`), previously documented above as
  staging-verification-only, becomes MVP1's actual identity mechanism too.
  A fixed small set of personas (Organizer, Scorekeeper, one or more
  Players) are pre-minted once (long expiry) via that same script.
- Phase 7's UI gets a persona switcher (dropdown) instead of a login flow —
  swaps which pre-minted token the API client attaches as the Bearer
  header. No `POST /login`-shaped endpoint is added to the backend; the
  app still only ever *validates* tokens (`NFR4` stays intact — minting
  happens outside the running app, via the offline script, not inside it).
- Pre-minted tokens are long-lived credentials (effectively permanent
  Organizer access) and must not be committed to git or baked into the
  public JS bundle — Helm-secret-injected at deploy time.
- Real SSO (Google or otherwise) is explicitly a separate, later
  initiative (the owner has other plans for it) — swapping it in later is
  a config change only (`OIDC_ISSUER`/`OIDC_JWKS_URL` pointed at a real
  IdP), *except* `identity_from_claims` (`app/auth/identity.py`) currently
  assumes `claims["sub"]` parses as a UUID, which breaks for Google's
  opaque numeric `sub` — flagged here so it isn't rediscovered from
  scratch when that work starts.
- Rejected for MVP1: standing up a real broker (Dex/Keycloak) — real OIDC
  end-to-end, but a new service to deploy/operate for a milestone that
  doesn't need multi-user trust boundaries yet. Rejected: pointing
  directly at Google now — same `sub`-is-not-a-UUID blocker plus no
  `organizer` role claim without either a Workspace custom claim or an
  in-app subject allowlist, for marginal benefit over the switcher given
  the private, disposable-data deployment target.

## 2026-08-05 — Phase 7 PR3: match `method` field, minimal not full reconciliation model

Match result reporting gets a `method` field (`Literal["manual_entry"]`
for now) so a future reporting method can be distinguished later without
another migration. A fuller dual-submission/dispute-reconciliation model
(player-vs-player conflicting claims in `confirmed_by`, a `status` field
separate from `result`, per-entry reporter authorization) was proposed
during design review and rejected for now: it solves a workflow with no
current UI, no player-submission endpoint, and no FR requiring it.
Tracked as a future GitHub issue instead of building ahead of need.
Confirmed with the owner 2026-08-05.

## 2026-08-05 — Phase 7 PR3: Scorekeeper UI gating by persona role, not per-pod self-check

Parent Phase 7 spec assumed `GET /pods/{id}/roles` could be used by a
Scorekeeper persona to self-check its pod role; that endpoint is actually
`require_pod_organizer`-gated (403 for Scorekeeper). Rather than add a new
backend self-check endpoint, PR3's UI gates the result-entry controls by
persona role alone (`organizer`/`scorekeeper` see them, `player` doesn't)
— convenience only, same as the rest of the RBAC-gating design; the
backend's `pod_staff_allowed` check remains the real enforcement.
Confirmed with the owner 2026-08-05.

## 2026-08-04 — Phase 7 PR2: msw for frontend component tests

Component tests for the Event/Pod/Entry setup screens mock HTTP at the
network layer via `msw` (`frontend/src/test/server.ts`) rather than
stubbing `AuthContext`'s `apiFetch` internals — tests exercise real
request/response shapes (URL, method, JSON body) the way the browser
actually sends them. Confirmed with the owner 2026-08-04, flagged in the
Phase 7 PR2 design spec's "New dependency" section.

## 2026-08-05 — Phase 7 PR4: Accept-header route dispatch, not /api namespace restructure

`/pods/:podId/report` collides with a real backend endpoint at the
identical path (`GET /pods/{id}/report`), the second such collision after
PR2's still-open `/events/:eventId`. Rather than a per-route contained fix
(PR3's regex carve-out doesn't generalize to a literal-path collision) or
the larger `/api` namespace restructure, nginx and Vite now dispatch on
the `Accept` request header instead of path: real browser navigation
sends `Accept: text/html`, the frontend's own `apiFetch` (`AuthContext.tsx`)
sends `Accept: application/json`. This replaces PR3's `/pairings` carve-out
and also retires the `/events/:eventId` collision — one mechanism covers
all three cases raised across PR2/PR3/PR4. The `/api` restructure remains
un-adopted. Confirmed with the owner 2026-08-05.

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

## 2026-08-08 — Phase 8: bye-only entries floor OMW%/OOMW% at the floor value, not 0.0

`OwpOomwTiebreak`'s opponent-average (`_average`) originally returned `0.0`
for an entry with zero real opponents faced (e.g. a round-1 bye recipient
before their first real match) — this inverted the "a bye is a win" intent,
ranking bye recipients below every equal-point entry with even a very weak
real opponent. The owner confirmed the fix: an empty opponent list floors
to `self.floor` (0.33 under MVP1's defaults), the same floor already
applied to individual opponents' own-MWP values elsewhere in the formula,
rather than asserting a raw 0.0. Confirmed with the owner 2026-08-08.
