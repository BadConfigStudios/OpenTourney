# Phase 16 — Login V2 deployment + frontend OIDC integration

## Context

Phase 15 (#86, merged) cut the backend over to validating real Zitadel-issued
tokens and confirmed the negative path live (a pre-cutover static-JWKS token
correctly `401`s). Full positive-path verification (real token → `200`) was
blocked by a gap discovered during that phase's manual verification (#82
comment, 2026-08-17): Zitadel v4's core binary no longer serves login pages
at all. Every `/oauth/v2/authorize` redirects to a separate **Login V2**
service — a standalone Next.js container this chart never deployed. Hitting
the endpoint directly returns `{"code":5,"message":"Not Found"}`.

This was flagged as a known-not-a-defect gap in Phase 14's PR (#84) but never
resolved. It blocks not just the frontend login button (this phase's
original scope per the parent design,
`2026-08-16-staging-zitadel-login-design.md`) but *any* real browser-based
login, including obtaining a token for curl testing. This spec folds
deploying Login V2 into Phase 16, ahead of the frontend work that depends on
it, and extends the parent design's Phase 16 bullet accordingly — the parent
design's frontend scope (`oidc-client-ts`, Login button, callback route,
retire `PersonaSwitcher`, expiry→logout) is unchanged and still governs
Section 3 below.

Research note: the infra design in Section 1 is grounded in Zitadel's own
`zitadel-charts` Helm chart source (`deployment_login.yaml`,
`configmap_login.yaml`, `secret_login-service-key.yaml`, `values.yaml`),
fetched and read directly — not paraphrased from third-party blog posts,
which turned out to describe a different (simpler, PAT-based) credential
scheme that the official chart doesn't actually use.

## Section 1 — Login V2 infra

**New Deployment** `<release>-zitadel-login`:
- Image `ghcr.io/zitadel/zitadel-login`, tag pinned to match core's tag
  (`v4.17.1` per current `values.yaml` — confirm the exact tag exists at
  plan/implementation time; the login image is versioned alongside core in
  the same Zitadel release).
- Port 3000. Env `NEXT_PUBLIC_BASE_PATH=/ui/v2/login`.
- Config supplied via a mounted `.env` file (ConfigMap), not plain container
  env vars — this matches the official chart's approach, since some values
  (`AUDIENCE`) are shell-interpolated from `ZITADEL_EXTERNALDOMAIN` at
  container start:
  - `ZITADEL_LOGINCLIENT_KEYFILE="/login-service-key/tls.key"`
  - `AUDIENCE="http://${ZITADEL_EXTERNALDOMAIN}"` (scheme/port following the
    existing `zitadel.externalSecure`/`externalPort` values)
  - `ZITADEL_API_URL="http://<release>-zitadel:8080"` (in-cluster core
    Service)
  - `CUSTOM_REQUEST_HEADERS="Host:${ZITADEL_EXTERNALDOMAIN},X-Zitadel-Public-Host:${ZITADEL_EXTERNALDOMAIN}"`

**New Service** `<release>-zitadel-login`, port 3000, same
component-label/selector pattern as the existing `zitadel-service.yaml`.

**New toggle**: `zitadel.login.enabled` in `values.yaml`, nested under the
existing `zitadel.enabled` gate, following the `zitadel.enabled`/
`percona.enabled` toggle-of-a-toggle precedent already in this chart
(`zitadel-deployment.yaml`'s `fail` guard).

**Auth into core (X.509 JWT via `SystemAPIUsers`)** — the official pattern,
not the PAT-based scheme some third-party writeups describe:
- Chart generates a self-signed RSA keypair at install time (Helm
  `genSelfSignedCert`, mirroring the cert-gen style already used elsewhere
  in this chart) into a new Secret with `tls.crt`/`tls.key` keys.
- `tls.crt` (public) mounts into the **core** Zitadel container; `tls.key`
  (private) mounts into the **login** container at
  `/login-service-key/tls.key`.
- Core's config gains a `SystemAPIUsers.login-client` entry: the cert path
  plus a `Memberships` grant of `IAM_LOGIN_CLIENT`. `SystemAPIUsers` is a
  dynamically-keyed map, which env vars can't express (this chart's core
  config today is 100% env-var-driven) — so this is the one new mechanism
  introduced: a small YAML file, mounted into the core pod, passed via a new
  `--config <path>` argument alongside the existing
  `start-from-init --masterkeyFromEnv` args. Everything else about core's
  config (env vars) is untouched.

**Enabling the Login V2 feature flag + base URI** — an instance-level
runtime setting (Zitadel's Instance Feature API), not static config.
bootstrap.py, already authenticated as `IAM_OWNER` via the FirstInstance
PAT, gains one more idempotent call: enable `loginV2` with `baseUri` set to
the in-cluster login Service's DNS name
(`http://<release>-zitadel-login:3000/ui/v2/login`).

**Readiness ordering**: the login pod's init container waits for core
Zitadel's readiness endpoint before starting (matches this chart's existing
liveness/readiness pattern on `zitadel-deployment.yaml`; exact probe
mechanism — reuse `/debug/healthz` via a simple wait loop rather than
introducing the official chart's `wait4x` tool dependency — decided in
planning).

**Out of repo**: external (Cloudflare tunnel) routing for core Zitadel and
Login V2 is *not* part of this chart or this phase — no ingress/tunnel
config exists anywhere in `charts/opentourney` today (that routing is
Fleet-managed, external to this repo, per existing prod-auth precedent). A
tester's browser reaching both endpoints is a manual operator prerequisite
for this phase's acceptance walkthrough, called out explicitly in the plan,
not something the plan implements.

## Section 2 — OIDC app registration (bootstrap.py)

`get_or_create_application()` (added in Phase 15 for the `opentourney-cli`
Native app) becomes parameterized by `(name, appType, redirectURIs)` instead
of hardcoded, and is called twice:

- **`opentourney-cli`** (existing, untouched): `OIDC_APP_TYPE_NATIVE`, kept
  exactly as Phase 15 left it, for curl/manual-token testing.
- **`opentourney-frontend`** (new): `OIDC_APP_TYPE_USER_AGENT` — Zitadel's
  recommended type for a browser SPA (see the trimmed comment Phase 15 left
  at `get_or_create_application()`, bootstrap.py:208-212) — public client,
  PKCE, `accessTokenType: OIDC_TOKEN_TYPE_JWT` (mandatory, same reasoning as
  Phase 15: Zitadel's default access token is opaque and the backend can
  only validate a JWT), redirect URI pointed at the frontend's new
  `/callback` route.

Both client_ids need to reach their consumers: `opentourney-cli`'s stays a
curl-testing value (documented, not shipped to any runtime config);
`opentourney-frontend`'s client_id is injected into the frontend's
`config.json` (new key alongside `personas` — exact shape decided in
planning, since `personas` itself is being retired per Section 3).

## Section 3 — Frontend (`oidc-client-ts`)

Unchanged from the parent design's original Phase 16 scope, restated here
for completeness now that Sections 1–2 unblock it:

- New dependency `oidc-client-ts`, Authorization Code + PKCE.
- `AuthContext.tsx` replaces persona-from-`config.json` state with a real
  OIDC session: holds the `oidc-client-ts` `User` (tokens + claims),
  `apiFetch` attaches `Authorization: Bearer <token>` — which of
  access/ID token the backend expects should already be settled by Phase
  15's `RemoteJWKSProvider`/`decode_token` usage; reuse that, don't
  re-decide it here.
- `PersonaSwitcher.tsx` retired; a new `LoginButton` calls
  `userManager.signinRedirect()`.
- New `/callback` route in `routes/router.tsx` calls
  `userManager.signinRedirectCallback()`, then routes into the app.
- Local `npm run dev` auth stays broken/unaddressed — pre-existing gap,
  explicitly out of scope (unchanged from parent design).

## Section 4 — Session/expiry behavior

Unchanged from the parent design, confirmed for this phase: on any `401`
response, or a locally-detected expired token (checked before each
`apiFetch` call), the frontend clears the stored session and immediately
calls `signinRedirect()` — no interstitial "session expired" screen. No
silent token renewal in this first cut (unchanged from parent design).

## Section 5 — Verification

- **Infra**: `helm template`/`helm lint` dry-run for the new Login V2
  resources before deploying. Deploy to staging; confirm the login pod
  reaches Ready; confirm core's `/oauth/v2/authorize` now redirects into
  `/ui/v2/login` instead of 404ing.
- **Backend**: complete the curl verification Phase 15 deferred — a real
  Zitadel-issued token (obtained through Login V2's page, or its token
  endpoint directly) → backend `200`. Manual, staging, same pattern as
  Phase 15's verification — not new CI/automated integration coverage.
- **Frontend**: unit tests for expiry-detection/redirect logic (existing
  test convention) and the OIDC callback flow against a mocked token
  endpoint (`msw`, existing convention).
- **Acceptance**: manual walkthrough — click Login, authenticate as each of
  the 3 test personas through Zitadel's real Login V2 page, confirm
  role-appropriate access, let a session expire, confirm it auto-redirects
  back to login.

## Sizing note

This spec covers a large diff: new chart resources (Deployment, Service,
Secret, config file, values), a bootstrap.py rework (parameterized app
registration + feature-flag call), and a frontend rewrite (new dependency,
new auth context, new route, component removal). Per the 600-line PR-size
guardrail, expect writing-plans to split this into 2+ PR-sized tasks (e.g.
infra + bootstrap.py first, frontend second) rather than one PR — this spec
describes the full scope; the plan decides the split.

## Out of scope (unchanged from parent design)

- Apple/Facebook federation (prod-only, later MVP).
- Silent token renewal.
- Local `npm run dev` auth setup.
- Per-customer-namespace prod Zitadel rollout.
- External (Cloudflare tunnel) routing for core Zitadel / Login V2 (Section 1).
- Issue #87 (bootstrap.py search pagination, duplicated create-or-find
  pattern, no unit tests) — deferred tech debt from Phase 15, not blocking,
  not addressed here.

## Open questions for the implementation plan (writing-plans)

- Exact Login V2 image tag to pin (confirm it matches core's `v4.17.1`).
- Exact readiness-wait mechanism for the login pod's init container
  (simple wait loop vs. adopting `wait4x`).
- Exact shape of the frontend's new OIDC config key(s) in `config.json`
  (replacing `personas`).
- Whether `AUDIENCE`'s scheme/port derivation needs new `values.yaml`
  fields or can reuse `zitadel.externalPort`/an implied default.
