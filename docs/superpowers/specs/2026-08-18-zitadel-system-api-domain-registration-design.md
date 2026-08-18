# Zitadel System API domain registration

## Context

Phase 16 PR1 (Login V2 infra, this branch) migrated `zitadel.externalDomain`
to the real public hostname (`opentourney-staging.badconfig.com`), required
so core's own anti-DNS-rebinding Host check and Login V2's server-generated
redirects work for a real external browser. That's confirmed working
end-to-end (full real browser login verified through the public domain,
Task 8).

It left one gap: the backend's own JWKS fetch (to validate tokens it
receives) is blocked both ways.

- **Public URL** (`https://opentourney-staging.badconfig.com/oauth/v2/keys`):
  Cloudflare's bot/TLS-fingerprint protection (error 1010) blocks Python's
  plain HTTP client.
- **Internal URL** (`http://zitadel:8080/oauth/v2/keys`, the in-cluster
  Service name): rejected with `404 Instance not found` by Zitadel's own
  Host-header check (`instance_interceptor.go` → `query.InstanceByHost`),
  because `zitadel` (the internal Service name) isn't a domain registered
  against this instance — only the public hostname is.

Two earlier fix attempts this session were root-caused and ruled out via
source reading (`zitadel/zitadel` v4.17.1, the exact deployed version):

- `AddTrustedDomain` (`POST /v2beta/instances/{id}/trusted-domains`) turned
  out to be an unrelated mechanism — its gRPC handler
  (`internal/api/grpc/instance/v2beta/domain.go`) calls
  `command.AddTrustedDomain`, a different command than the one
  `query.InstanceByHost` actually reads from.
- The correct endpoint, `AddCustomDomain`
  (`POST /v2beta/instances/{id}/custom-domains` → `command.AddInstanceDomain`,
  the same command that feeds `InstanceByHost`), requires permission
  `system.domain.write`. Live-tested with `bootstrap.py`'s existing PAT
  (which already has `iam.write`, confirmed via the trusted-domains call
  succeeding) and got `403 AUTH-5mWD2: No matching permissions found`.

`system.domain.write` is granted by exactly one built-in Zitadel role:
`SYSTEM_OWNER` (confirmed in `cmd/defaults.yaml`'s
`InternalAuthZ.RolePermissionMappings` — no other built-in role includes
it). `SYSTEM_OWNER` requires `MemberType: System` in `SystemAPIUsers`
config, Zitadel's separate machine-to-machine auth mechanism (JWT Bearer /
RFC 7523, not PAT-based). This deployment is single-tenant (one Zitadel
instance), so the practical blast radius of a `SYSTEM_OWNER` credential is
"this one instance" regardless of the role's nominal scope.

## Design

### Keypair

One RSA keypair, generated once via `openssl` this session, never committed
to git (same handling as `zitadel.masterkey`/admin password today — real
values only ever exist as `--set-string` CLI args and live k8s Secret data,
never in a tracked file).

### Zitadel core config

`charts/opentourney/templates/zitadel-secret.yaml` gains two new
`stringData` keys, following the exact pattern `ZITADEL_MASTERKEY` already
uses:

- `ZITADEL_SYSTEM_API_PRIVATE_KEY` — consumed only by the `bootstrap`
  sidecar container.
- `ZITADEL_SYSTEM_API_PUBLIC_KEY` — consumed only by the `zitadel` core
  container, templated into a `ZITADEL_SYSTEMAPIUSERS` env var:
  ```
  ZITADEL_SYSTEMAPIUSERS={"opentourney-bootstrap":{"KeyData":"<base64 pubkey>","Memberships":[{"MemberType":"System","Roles":["SYSTEM_OWNER"]}]}}
  ```

### bootstrap.py

- New pip dependency: `pyjwt[crypto]` (added to the script's existing
  one-shot `pip install` line alongside `requests`).
- New function `get_system_api_token(session)`: builds a signed JWT
  assertion (`iss=sub="opentourney-bootstrap"`, `aud=<issuer>`, short
  expiry), POSTs it to `/oauth/v2/token`
  (`grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&scope=openid`),
  returns the resulting access token.
- `add_trusted_domain` (currently calling the wrong endpoint) is replaced
  by `add_custom_domain(session, instance_id, domain)`, calling
  `POST /v2beta/instances/{id}/custom-domains` with the system API token as
  Bearer instead of the PAT. Same idempotent-no-op handling as today, but
  for whatever status/message Zitadel actually returns for
  already-registered custom domains (to be confirmed live — the 400
  `Errors.Instance.Domain.AlreadyExists` behavior seen for trusted-domains
  may or may not carry over; verified during implementation, not assumed).
- `main()`'s call site: `add_trusted_domain(session, instance_id, "zitadel")`
  → `add_custom_domain(session, instance_id, "zitadel")`.

### staging-upgrade.sh

Two new `secret()` reads for the new keys, passed through as
`--set-string` alongside the existing four. First-ever rollout after this
change seeds them manually with the freshly generated keypair (one-time,
documented in the SDD ledger, not committed); every rollout after that
self-perpetuates via the live-secret read, same as today.

### Error handling

Same convention as every other `bootstrap.py` helper: a real
auth/permission failure raises and fails the bootstrap container loudly
(visible in pod logs, no silent swallowing). Only a confirmed
already-registered response is treated as a no-op.

### Testing

No unit-test infrastructure exists for `bootstrap.py` (confirmed — none of
this PR's Tasks 1-7 added any; it's a Helm-hook script validated by live
cluster verification only). This change stays consistent with that:
verified by redeploying to `opentourney-staging`, tailing the bootstrap
sidecar log for a clean `add_custom_domain` success/no-op line, and curling
`http://zitadel:8080/oauth/v2/keys` from a throwaway debug pod to confirm
the JWKS response is no longer a 404.

## Out of scope

- Any change to backend application code (`RemoteJWKSProvider` already
  handles any RS256 issuer/audience/JWKS combination correctly).
- Removing or rotating the System API credential after first use — it
  stays live for idempotent reruns across pod restarts, matching the
  masterkey/admin-password pattern.
- Solving the public-URL Cloudflare 1010 block — the internal path fully
  replaces the need for it.
