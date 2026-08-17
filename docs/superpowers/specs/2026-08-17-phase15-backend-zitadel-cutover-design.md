# Phase 15 — Staging backend cutover to Zitadel

## Context

Phase 14 (#84, merged) deployed self-hosted Zitadel into `opentourney-staging`
and bootstrapped a project, 3 roles, 3 test users, and a Complement Token
Action that stamps `roles` + `source_system: "zitadel"` claims onto issued
tokens. It explicitly left one gap, documented in the PR as a known-not-a-defect:
no OIDC application (client) exists yet, so no token could be minted to
verify the roles-claim flow end to end. Login V2 UI wasn't confirmed
reachable and ROPC (direct password grant) is unsupported by Zitadel by
design.

This phase (issue #81, FR35) is scoped by the parent design
(`2026-08-16-staging-zitadel-login-design.md`) as: swap the backend's Helm
secret from static JWKS to Zitadel's real issuer/audience/JWKS URL, verified
via curl using a token obtained through a real Zitadel login. That parent
design assumed an OIDC client already existed to obtain such a token from.
It doesn't. This spec closes that gap as part of Phase 15, since Phase 15 is
the first point in the phase breakdown where a real token is actually needed.

Backend code itself needs zero changes — `RemoteJWKSProvider`
(`backend/app/auth/jwks.py`) and `decode_token` (`backend/app/auth/oidc.py`)
already validate any RS256 issuer/audience/JWKS combination. Everything in
this spec is chart, bootstrap script, and documentation work.

## OIDC client registration (bootstrap.py)

`charts/opentourney/files/bootstrap.py` gains a `get_or_create_application()`
step, following the existing idempotent get-or-create pattern used for the
project/roles/users/action (409 on create → resolve existing ID via search).

- **App type: Native.** Public client, PKCE, no client secret to manage or
  leak. Matches the flow this phase's manual curl verification needs, and
  the same client type/flow `oidc-client-ts` (Phase 16 frontend) will use —
  no throwaway client to replace later.
- **`accessTokenType: OIDC_TOKEN_TYPE_JWT`.** Mandatory, not optional:
  Zitadel's default access token is opaque, which the backend's RS256/JWKS
  verification cannot validate at all. Without this setting the whole cutover
  is a dead end regardless of what issuer/audience values are configured.
- **Redirect URI**: a loopback address (`http://localhost:8765/callback`).
  Nothing needs to actually listen on that port for this phase — the
  Authorization Code lands in the browser's address bar on redirect (as a
  404, since nothing's listening) and is copied out manually for the curl
  token exchange.
- Logs the resulting `client_id` to stdout once, on the create path only,
  next to the existing test-user-password log lines (same rationale: not
  retrievable from Zitadel after creation, never written to a file or
  committed).

## Helm / deploy changes

No `secret.yaml` template changes — it already branches on
`.Values.secrets.oidcJwksUrl` vs `.Values.secrets.oidcJwksStatic`, and
`oidcIssuer`/`oidcAudience` are already required plain values. Only the
deploy-time values change:

- `secrets.oidcIssuer` = Zitadel's external domain value already configured
  on the Deployment (`.Values.zitadel.externalDomain`, defaulting to
  `http://zitadel.<namespace>.svc.cluster.local:<port>` — in-cluster only,
  consistent with no public hostname existing yet).
- `secrets.oidcAudience` = the `client_id` logged by bootstrap.py's new step.
- `secrets.oidcJwksUrl` = `<issuer>/oauth/v2/keys` (Zitadel's fixed JWKS
  endpoint path), used in place of `secrets.oidcJwksStatic`.

`DEVELOPMENT.md`'s documented `helm upgrade --install` example is updated to
drop the `secrets.oidcJwksStatic=<oidc-jwks-static-json>` flag and add the
three flags above.

**Bootstrap-then-configure ordering gotcha** (documented inline in
`DEVELOPMENT.md`, same shape as the existing masterkey-reuse caveat): on a
*fresh* Zitadel stand-up, the client doesn't exist until after the first
`helm upgrade` brings the Zitadel pod up and its bootstrap sidecar runs —
so `secrets.oidcAudience` can't be correct on that very first apply. The
practical sequence is: deploy once (Zitadel comes up, bootstrap creates the
client, `client_id` appears in pod logs), read the logged `client_id`, then
`helm upgrade` again with `secrets.oidcAudience` set correctly. Because
`get_or_create_application()` is idempotent, ordinary re-deploys against an
already-bootstrapped instance never hit this — only a full teardown/rebuild
does, which is already the documented rare case for the masterkey.

## Verification workflow (new DEVELOPMENT.md section)

Manual recipe, since Login V2 UI accessibility from outside the cluster is
exactly what was unverified after Phase 14:

1. `kubectl --context mcgee-local -n opentourney-staging port-forward svc/zitadel 8080:8080`
2. Zitadel enforces anti-DNS-rebinding Host-header validation against
   `ZITADEL_EXTERNALDOMAIN` — either add a temporary `/etc/hosts` entry
   mapping that hostname to `127.0.0.1`, or use `curl --resolve` /
   browser-equivalent for the browser-driven steps.
3. Build a PKCE code verifier/challenge, open
   `http://<externalDomain>:8080/oauth/v2/authorize?client_id=<id>&redirect_uri=http://localhost:8765/callback&response_type=code&scope=openid+profile&code_challenge=<...>&code_challenge_method=S256`
   in a browser, log in as `organizer@staging.local` with the password
   bootstrap.py logged.
4. Copy the `code` param from the resulting (unlistened, 404) redirect URL.
5. Exchange it via `curl` against `<externalDomain>:8080/oauth/v2/token`
   (Authorization Code + PKCE, no client secret).
6. `curl` the backend with the resulting access token as a Bearer token;
   confirm 200 and correct identity/role resolution (organizer role present,
   `source_system: "zitadel"` accepted by `identity_from_claims`).

This closes PR #84's documented known-gap (roles-claim decode never verified
against a real issued token) and satisfies issue #81's "verified via curl"
acceptance criterion.

## Testing

- No backend code changes, so `backend/tests/unit/test_oidc.py` needs no new
  cases — confirm the existing suite still passes (no regression), per the
  parent design.
- The live curl walkthrough above is the actual verification for this phase
  and is manual by nature (matches this phase's scope: prove the plumbing
  with a human-driven login, not build automation for it — that's Phase
  16's frontend flow).
- `helm lint` / `helm template --set zitadel.enabled=true` re-run clean after
  the bootstrap.py change, matching Phase 14's existing test-plan pattern.

## Out of scope for this spec

- Frontend OIDC integration (`oidc-client-ts`, Login button, callback route)
  — Phase 16.
- Automating the curl verification into CI — no CI-reachable Zitadel
  instance exists (staging is a manual `helm upgrade` deploy, per
  `DEVELOPMENT.md`).
- A public hostname / Cloudflare Tunnel for Zitadel — the verification
  recipe above works around its absence via port-forward; assigning one is
  unscoped, tracked nowhere yet.
- Self-wiring `client_id` into the backend secret automatically (e.g. via
  `secretKeyRef` against a Secret bootstrap.py writes, mirroring the
  existing PAT-persistence pattern). Considered and explicitly rejected for
  this phase in favor of the manual flow, matching the existing
  masterkey/admin-password precedent — revisit if the manual step becomes a
  recurring pain point once Phase 16 or prod rollout depends on it.
