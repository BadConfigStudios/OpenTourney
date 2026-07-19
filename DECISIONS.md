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

## 2026-07-19 — MVP1 scope: BO1 only, Organizer-driven registration only

Best-of-three and self-service player registration are both deferred to
future MVPs, to keep MVP1's Match model and RBAC-gated entry-creation flow
simple. Neither blocks running a real event — an Organizer/Scorekeeper can
still register players manually at check-in.
