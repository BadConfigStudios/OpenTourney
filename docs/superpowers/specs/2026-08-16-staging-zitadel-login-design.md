# Staging real login via self-hosted Zitadel

## Context

Staging's persona-switcher (FR26) issues pre-minted JWTs via `mint_test_token.py`,
Helm-injected into the frontend's `config.json` at container start (fixed in
PR #78, closing #76). Those tokens have a fixed expiry (1hr default, the CLI
never exposed `--expires-in`) and once expired there is no way back in short
of an operator re-minting and redeploying by hand — `apiFetch` doesn't detect
expiry, it just lets the resulting 401 fall through as a generic error.

The immediate ask ("keep the signature refreshing") could be solved by
re-minting with a long expiry. Instead, this spec adopts a different fix:
bring real OIDC login (Zitadel) into staging now, ahead of its originally
scoped prod-only timeline.

## Supersedes: DECISIONS.md 2026-08-09 ("Staging keeps today's static-JWKS
persona-switcher... no broker... consistent with minimizing staging's
external dependencies")

That decision is explicitly reversed here, by the owner, with full awareness
of what it overrides. The reasoning for reversal: minimizing staging's
external dependencies is worth less than staging actually exercising the same
login architecture prod will run, given prod's Zitadel component was already
designed (just unscheduled) and staging is the natural place to prove it out
first. Everything else about the original 2026-08-09 decision (broker choice,
deployment shape, DB reuse) still holds — this spec **implements** that
decision early, applied to `opentourney-staging` first, rather than
inventing new architecture.

## Architecture

- **Zitadel**: a `zitadel.enabled` toggle in `charts/opentourney`, same
  pattern as the existing `percona.enabled` toggle (`{{- if .Values.zitadel.enabled }}`
  guarding new templates). Single lightweight Go binary, deployed as its own
  Deployment/Service in the `opentourney-staging` namespace — not a new
  namespace, not a new chart. Reuses `opentourney-staging`'s existing Percona
  Postgres cluster (`opentourney-staging-pg`) via its own schema, per the
  original decision — no second `PerconaPGCluster`.
- **Backend**: zero code changes. `RemoteJWKSProvider` (`backend/app/auth/jwks.py`)
  already handles any real issuer. Staging's Helm secret swaps
  `OIDC_JWKS_STATIC` for `OIDC_ISSUER`/`OIDC_AUDIENCE`/`OIDC_JWKS_URL`
  pointed at Zitadel's discovery/JWKS endpoints.
- **Frontend**: `oidc-client-ts` (new `package.json` dependency, confirmed —
  this becomes real, permanent auth plumbing shared with prod's eventual
  Google/Apple/Facebook login, not disposable test code) implements
  Authorization Code + PKCE. A "Login" button redirects to Zitadel's real
  hosted login page. A tester authenticates as one of 3 provisioned test
  accounts (organizer/scorekeeper/player). A callback route exchanges the
  code, stores the resulting token (same `localStorage` persistence pattern
  `AuthContext.tsx` already uses for the persona choice).
- **Test user/role provisioning**: an automated bootstrap Job calling
  Zitadel's management API, run once per environment stand-up, declaratively
  creating the OpenTourney project, its 3 roles (organizer/scorekeeper/player),
  and the 3 test accounts. Reproducible across staging teardown/rebuild —
  the same script becomes the template for prod's later per-customer
  namespace bootstrap.
- **Role claims**: Zitadel Project Roles assigned per test user, asserted
  into the ID token in the shape `identity_from_claims`
  (`backend/app/auth/identity.py`) already expects: `claims["roles"]`
  containing `"organizer"` for the Organizer test account, empty/other for
  Scorekeeper and Player (matching how `mint_test_token.py`'s `--organizer`
  flag works today — scorekeeper/player authorization is resolved via
  org-membership DB state, not the JWT itself). `identity_from_claims` also
  requires a `source_system` claim (part of the composite key every
  `OrganizationMember`/`PodRole` grant is keyed on) — the Complement Token
  Action asserts a fixed `source_system: "zitadel"` alongside `roles`.

## Session / expiry behavior

Expiry behaves like logout, not like an error state:

- On any 401 response, or a locally-detected expired token (checked before
  each `apiFetch` call), the frontend clears the stored session and routes
  back to the login screen (or immediately re-triggers the Zitadel redirect —
  implementation detail for the planning phase).
- No silent token renewal in this first cut — a tester re-authenticates
  through Zitadel's login page when a session lapses, matching the
  low-frequency nature of manual staging verification. Silent renew (which
  `oidc-client-ts` supports for free) is a candidate follow-up, not required
  for this spec.

## Testing

- **Unit**: role-claim mapping (`identity_from_claims` already has coverage —
  verify no regression), frontend expiry-detection/redirect logic.
- **Integration**: backend `decode_token` against a token actually issued by
  a running Zitadel instance in CI/staging (extends the existing
  `test_oidc.py` real-RSA-keypair pattern, or a live call in staging
  verification — decide in planning), frontend OIDC callback flow against a
  mocked token endpoint (`msw`, per the existing frontend test convention).
- **Acceptance**: manual walkthrough — click Login, authenticate as each of
  the 3 personas through Zitadel's real page, confirm role-appropriate access,
  let a session expire and confirm it routes back to login.

## Phase breakdown

Three independently shippable phases, inserted before the current Phase 14,
pushing Pokémon `GameModule` (14) and everything after it down by three
(new Phase 17: Pokémon `GameModule`, 18: tiebreaks, 19: Google OIDC, 20: MVP2
verification).

1. **Phase 14 — Zitadel infra**: `zitadel.enabled` chart component, schema
   in the existing staging Postgres, bootstrap Job creating the project/roles/
   test users. Verified standalone via Zitadel's own login page — no
   OpenTourney frontend involved yet.
2. **Phase 15 — Backend cutover**: staging's Helm secret swaps static JWKS
   for Zitadel's issuer/JWKS URL. Verified via curl, using a token obtained
   through a real Zitadel login (manual, via Zitadel's page or its token
   endpoint directly).
3. **Phase 16 — Frontend OIDC integration**: `oidc-client-ts`, Login button,
   callback route, retire the old `PersonaSwitcher`, expiry→logout handling.

## Relationship to FR30 (Phase 16 → renumbered 19, Google OIDC for prod)

This work builds the frontend OIDC Authorization Code/PKCE plumbing FR30
will also need — Zitadel and Google both speak standard OIDC, so the same
`oidc-client-ts` integration is very likely reused, just pointed at a
different issuer/client_id via config. FR30's remaining scope when reached
should shrink accordingly (prod Zitadel deployment + Google federation
config, not a frontend rebuild) — worth re-scoping FR30 explicitly when that
phase is picked up, not rewritten speculatively here.

## Out of scope for this spec

- Apple/Facebook federation (prod-only, later MVP per `REQUIREMENTS.md`).
- Silent token renewal.
- Local `npm run dev` auth setup (pre-existing gap, unrelated to this work).
- Per-customer-namespace prod Zitadel rollout — this spec only stands up
  `opentourney-staging`'s instance.

## Open questions for the implementation plan (writing-plans)

- Exact Zitadel Helm values (image, resource requests/limits, PVC sizing if
  any beyond the reused Postgres schema).
- Bootstrap Job's exact API calls / idempotency (safe to re-run against an
  already-bootstrapped instance).
- Whether the frontend redirect-back-to-login on expiry happens automatically
  or shows an interstitial "session expired" screen first.
