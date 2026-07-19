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

## Authentication and authorization

OpenTourney separates *authentication* (who someone is — not its job) from
*authorization* (what they can do within OpenTourney — its job entirely).

- **Authentication**: the calling host system authenticates the user and
  passes OpenTourney a trusted identity assertion. OpenTourney has no
  accounts, login, or passwords of its own, and never re-implements
  authentication — every client integrates with its own auth provider,
  not OpenTourney's.
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

Host applications integrate as thin clients only:

1. **Instantiate** — create an Event/Pod via the API, mapping the host
   app's own roster/org data to opaque player references.
2. **Interface** — render UI (scorekeeper screens, standings, brackets) by
   reading OpenTourney's API.

No tournament logic or state lives in the host app. The first intended
consumer is a check-in/club-management app, integrated this way — but
OpenTourney has no dependency on it and no knowledge of its data model.

## Open questions

- API shape/versioning conventions.
- Storage/deployment stack (not yet decided).
- Whether/when to revisit federation and shared analytics as a later
  phase.
