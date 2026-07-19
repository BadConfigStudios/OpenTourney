# OpenTourney

An open, game-agnostic tournament engine and data standard. OpenTourney runs
tournaments (Swiss, single elimination, double elimination, multi-phase) and
tracks pairings, results, and standings as a standalone HTTP service — not
tied to any single game, host application, or identity provider.

## Status

Design stage. No implementation yet. This README captures the domain model
and design decisions as agreed so far, ahead of writing any code.

## Why

Built to decouple "running and tracking a tournament" from any specific
platform (e.g. [play.limitlesstcg.com](https://play.limitlesstcg.com)) or
host app. Host applications (check-in systems, club management tools,
websites) integrate with OpenTourney as thin clients — they instantiate
tournaments and render UI against its API, but own none of the tournament
logic or state themselves. Any app, in any language, can be an OpenTourney
client by implementing against the API contract; that's what makes it a
standard rather than a library tied to one app's stack.

## v1 scope

The bar for v1 is "run one real event end-to-end," not the full design
below. Everything else in this doc is real intended scope, just staged —
see Roadmap at the end for what's deferred and why, and for where a new
contributor could pick up a self-contained piece of it.

v1 includes:

- Domain model: Event, Pod, Entry, Player reference, Round, Match (all
  four formats — Swiss/single-elim/double-elim/multi-phase — since
  pairing generation is known algorithms, not open design work).
- Operational API, published and documented from day one (see API-first
  design) — this is core, not deferred, since an undocumented API is
  what makes a project hard for anyone else to build against.
- RBAC (Organizer/Scorekeeper/User), with a single standards-based auth
  mechanism (OIDC) — enough to prove the authorization model works.
  Additional auth standards (SAML, LDAP) are staged, see Roadmap.
- A minimal operational UI: setup, pairings, and scoring — functional,
  not yet the venue-display presentation mode (see Roadmap).
- Match result reporting with full provenance (`reported_by`,
  `witnessed_by`, `confirmed_by`) — core to the data model, not
  deferrable.

Deferred to post-v1 (staged, see Roadmap): additional auth standards,
the embeddable UI module, presentation-mode display, and the public
meta/analytics API.

## API-first design

The HTTP API is the actual product; everything else is a client of it —
including OpenTourney's own operational UI. The reference UI gets no
private/backend-only access that the published API doesn't also expose.
If the reference UI needed shortcuts to work, the API wouldn't actually
be sufficient for third-party clients either, and "open standard" would
be aspirational rather than true.

This requires, as first-class deliverables (not written after the fact
once an implementation exists):

- A published, versioned API specification (e.g. OpenAPI/Swagger), kept
  current with the implementation rather than describing intent.
- The domain model (below) published as a formal, standard schema — not
  just prose — so any client can generate types or validate against it
  directly.
- Documentation covering both the API and the data model, maintained
  alongside the code.

## Non-goals (for now)

- **Not decentralized/federated hosting.** Each deployment is a single
  service instance for one operator. Federation, cross-instance trust, and
  a shared meta-analytics layer are a possible future phase, not a v1
  requirement.
- **Not an authentication provider.** OpenTourney has no accounts, no
  login, no passwords. It trusts an identity assertion (e.g. a signed
  token) issued by whatever host system authenticated the caller, and
  never re-implements that authentication itself. (It does own its own
  *authorization* model — see RBAC below — that's a different concern
  from authenticating who someone is.)
- **Not a full game-rules engine.** OpenTourney doesn't simulate or validate
  gameplay. Deck/game metadata is descriptive (what was played), not
  enforced (whether the deck/plays were legal). Rules-accurate validation,
  if ever needed, is a separate concern.

## Domain model

- **Event** — a tournament instance (a date, a set of pods).
- **Pod** — a division/bracket within an event (e.g. by age division,
  skill level, or just "everyone playing this format"). Round count and
  pairing structure are computed per pod from its entry count and format
  (Swiss / single-elim / double-elim / multi-phase).
- **Entry** — a player's participation in a pod: player reference, game,
  format, and what they're playing (e.g. a decklist), scoped to that pod.
- **Player reference** — `(player_uuid, source_system)`. Opaque and
  external. OpenTourney does not authenticate players; it just needs a
  stable reference supplied by the calling system, which it then binds to
  a role (see RBAC below).
- **Round** — a numbered round within a pod, generated according to the
  pod's format.
- **Match** — a pairing within a round, plus its result (win/loss/tie) and
  reporting provenance.

## Operational web UI

OpenTourney ships its own first-party, web-driven UI for running an
event — this is core scope, not optional tooling bolted on later. It
covers:

- **Setup** — create an event for a given date; add one or many pods to
  it, each with its own game and format type (Swiss, single-elim,
  double-elim, multi-phase).
- **Pairings** — viewable per round, filterable by pod/game. **v1** is a
  standard screen view; a **presentation mode** suited to a venue
  display (TV/projector) is a staged roadmap item, not required to run
  an event.
- **Scoring** — match result entry and adjudication, gated by the RBAC
  roles above (Organizer/Scorekeeper enter or adjudicate; Users see
  their own matches and standings).

This is distinct from the analytics/meta dashboard described below,
which is explicitly out of scope for OpenTourney itself. A host app can
still integrate directly against the API for a fully custom experience
(see Integration model), but OpenTourney's own UI is a complete way to
run an event on its own, not just a fallback.

## Authentication and authorization

OpenTourney separates *authentication* (who someone is — not its job) from
*authorization* (what they can do within OpenTourney — its job entirely).

- **Authentication**: the calling host system authenticates the user and
  passes OpenTourney a trusted identity assertion. OpenTourney has no
  accounts, login, or passwords of its own, and never re-implements
  authentication — every client integrates with its own auth provider,
  not OpenTourney's. This should be standards-based rather than a
  bespoke token format, so any host's existing identity infrastructure
  can integrate directly. **v1 ships OIDC only**, enough to prove the
  model works end-to-end; SAML and LDAP-backed support are staged as
  separate, self-contained roadmap items (see Roadmap) rather than
  built simultaneously with the core.
- **Authorization (RBAC)**: OpenTourney maps each authenticated identity to
  a role, scoped per event/pod:
  - **Organizer** — create/manage events, pods, and entries.
  - **Scorekeeper** — act as a trusted witness; enter or adjudicate match
    results for pods they're assigned to.
  - **User/Player** — view standings; self-report or confirm their own
    matches; nothing beyond that.

  This is what makes the reporting/provenance model (below) actually
  enforceable rather than self-declared: a `witnessed_by` value is only
  meaningful if OpenTourney can verify the witness genuinely holds the
  Scorekeeper role for that pod, not just that someone claimed to.

## Public meta/analytics access

**Staged as a roadmap item** — depends on the operational API existing
first and having real event data to aggregate from, and on resolving the
sample-size question below. Not required for v1.

OpenTourney exposes two distinct API surfaces, not one API with optional
filtering:

- **Operational API** — private, RBAC-gated (see above). Events, pods,
  entries, matches, player references. This is where PII-adjacent data
  lives.
- **Meta/analytics API** — public, read-only, aggregated. Deck archetype
  win rates, meta share by format, matchup spreads, and similar
  statistics, computed server-side from operational data.

The meta API never returns player references, match-level rows, or
anything else that ties a result to an individual — not because those
fields are filtered out, but because the aggregation boundary between the
two surfaces means there's nothing to filter: the public API is generated
from aggregates, not from redacted operational records.

OpenTourney's own responsibility ends at computing and serving these
aggregates correctly — it has no analytics/meta dashboard or trend
reporting of its own (that's distinct from the operational UI below).
Presenting, further aggregating, or trending meta data is a separate
concern for whatever consumes the public API. This also means
cross-instance meta analysis (aggregating public data across multiple
independent OpenTourney deployments) can be built entirely outside
OpenTourney later, without OpenTourney itself needing to solve federation
(see Non-goals).

Opaque player references are still stable per-player identifiers even
without a name attached, and correlating them across matches/events is a
re-identification risk in its own right — a reason to keep them out of
the public surface entirely, not just mask them.

A related risk at small scale: a pod with only a handful of entries can
make a stat identifying by context alone (e.g. "the one deck that went
3-0 in a 4-player pod"), even with zero player references in the
response. Whether/how to gate that (a minimum sample-size threshold
before a stat is surfaced publicly) is an open question — see below.

## Match result reporting

Result reporting must support multiple channels, since not every event
(or every player) can support the same technology — notably, in-person
youth events where players can't or shouldn't be expected to have their
own mobile devices.

Supported channels (v1, non-exhaustive):

- Verbal report to a scorekeeper (both players present)
- Signed paper match slip, entered by a scorekeeper (live or batched
  after the round)
- Mobile self-report (either player, or both)

The trust signal isn't the channel itself — it's whether both players'
agreement was actually captured. Underneath all three channels, a `Match`
result carries:

- `reported_by` — who submitted the result
- `witnessed_by` — an optional neutral third party (e.g. scorekeeper)
  present at reporting
- `confirmed_by` — which player(s) agreed to the result, regardless of
  medium (spoken, signed, tapped)

A scorekeeper-witnessed result with both players' verbal or signed
agreement is at least as trustworthy as an unwitnessed mobile
dual-confirmation — the witness and dual-confirmation are the trust
signal, not the transport.

This provenance data is also the intended foundation for a possible future
meta-analytics layer (aggregating decklist/result data across many
events): results with stronger provenance (witnessed + dual-confirmed)
would carry more weight than a single unilateral report, as one piece of
a broader fraud-resistance approach (also likely to include
instance/operator reputation and structural plausibility checks — not
solved here, noted for later).

## Integration model

OpenTourney's own operational UI (above) is a complete way to run an
event without any host app at all. Host applications are optional, and
when present integrate as thin clients only — never owning tournament
logic or state themselves:

1. **Instantiate** — create an Event/Pod via the API, mapping the host
   app's own roster/org data to opaque player references.
2. **Interface** — three options, not mutually exclusive:
   - **Standalone** — link out to OpenTourney's own hosted UI. (v1)
   - **Fully custom** — render a bespoke UI by reading OpenTourney's API
     directly, using none of its UI. Available from v1, since the API
     is published and documented from day one.
   - **Embedded module** — mount OpenTourney's operational UI (or scoped
     pieces of it, e.g. just pairings or just scoring) directly inside
     the host platform's own UI/navigation. Staged as a roadmap item —
     needs an actual embed mechanism (e.g. a JS SDK or web component)
     built and documented as its own piece of work.

The first intended host-app consumer is a check-in/club-management app —
but OpenTourney has no dependency on it and no knowledge of its data
model, and works standalone without it.

## Roadmap

Staged, in-scope work after v1 ships — each item is meant to be a
self-contained enough chunk that a new contributor could pick one up
without needing to understand or touch the others:

- **SAML support** — additional auth standard alongside v1's OIDC.
- **LDAP-backed auth support** — same, for LDAP-backed identity setups.
- **Embeddable UI module** — JS SDK / web component for mounting
  OpenTourney's UI (or scoped pieces of it) inside a host app. Known
  interested consumers: club-checkin (confirmed); PrizeMap.app (maybe —
  discussed with their lead/sole developer, who's independently run into
  similar issues with Limitless's organizer application process);
  possibly twinleafgg. Real demand, not speculative, and a good check
  that the design doesn't assume any one host's auth/UI stack.
- **Presentation mode** — venue-display (TV/projector) view for
  pairings, beyond v1's standard screen view.
- **Public meta/analytics API** — the aggregated, PII-free surface
  described above, including resolving the small-sample
  re-identification question before anything is exposed publicly.
- **Federation / cross-instance analysis** — see Non-goals; revisit only
  once a separate analytics platform exists and there's real demand for
  it, not before.

This list is intentionally not prioritized/ordered yet — order will
depend on who shows up wanting to work on what.

## Open questions

- API shape/versioning conventions.
- Storage/deployment stack (not yet decided).
- Whether/when to revisit federation and shared analytics as a later
  phase.
- Minimum sample-size threshold (or other mechanism) before a meta stat
  is exposed on the public API, to avoid small-pod re-identification.
- API spec format/tooling (e.g. OpenAPI version) and where the published
  spec/docs are hosted.
