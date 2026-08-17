# Development & Deployment

## Local development

See `backend/` and `frontend/` for their own dev setup (`pip install -e ".[dev]"` /
`npm install`). Both run standalone via their existing (non-prod) `Dockerfile`s.

The frontend's dev server (`npm run dev`) and the prod nginx container both proxy
`/events`, `/pods`, `/entries`, and `/matches` to the backend (`http://localhost:8000`
in dev via `vite.config.ts`'s `server.proxy`, `http://backend:8000` in the cluster via
`nginx.conf`), since the backend mounts its routers directly under those prefixes with
no `/api` namespace. Several SPA client-side routes collide with backend routes at the
exact same path (`/events/:eventId` vs. `GET /events/{id}`, `/pods/:podId/report` vs.
`GET /pods/{id}/report`) — both nginx.conf and vite.config.ts resolve this by
dispatching on the `Accept` request header rather than the path: real browser
navigation (hard refresh, direct link) sends `Accept: text/html,...` and is served the
SPA, while the frontend's own API calls send `Accept: application/json` (see
`AuthContext.tsx`'s `apiFetch`) and are proxied to the backend. One edge case: a
non-browser HTTP client hitting either collided path without an explicit
`Accept: text/html` (e.g. plain `curl`) is routed to the backend, not the SPA — correct
behavior for an API consumer, just worth knowing if debugging a "why did I get JSON
instead of the app" report. A proper `/api` namespace on the backend would remove the
ambiguity entirely; that's out of scope here.

## Staging deployment

Staging deploys the current feature branch to the cube cluster (k3s on openSUSE
MicroOS) **before** merging to `main`, so changes are validated against a real
cluster and real Postgres prior to merge. This is a manual `helm` workflow —
staging is not managed by Fleet/GitOps (no production release exists yet; that
lands with the `v0.1.0` cut in Phase 9).

### Prerequisites

Check these before the first `helm upgrade --install` in a namespace — both
will fail the deploy if unmet, and neither failure is obvious from the error
alone:

- **Percona PG Operator CRD installed and watching the namespace.** The chart's
  `PerconaPGCluster` resource (`pgv2.percona.com/v2`) requires the Percona PG
  Operator v3 CRD to already be installed and watching the target namespace,
  or `helm upgrade` aborts with "resource mapping not found." Since nothing in
  Phase 2 actually consumes the database yet (no domain models, no Alembic),
  a Postgres-less staging bring-up is a valid fallback: add
  `--set percona.enabled=false` to the `helm upgrade` command below.
- **GHCR pull secret named `ghcr-pull` in the `opentourney-staging` namespace.**
  Confirmed required by an actual staging deploy: the cube cluster has no
  node-level or default-ServiceAccount credential covering brand-new GHCR
  packages, so the very first deploy failed with `ErrImagePull` /
  `401 Unauthorized` until a namespaced pull secret was created. (The org's
  packages default to `internal` visibility on first push, not `private` —
  visibility didn't matter here; the cluster still needs an explicit
  credential either way.) `charts/opentourney/values.staging.yaml` already
  wires `imagePullSecrets: [{name: ghcr-pull}]`, so create the secret once
  per namespace before the first deploy:

  ```bash
  kubectl -n opentourney-staging create secret docker-registry ghcr-pull \
    --docker-server=ghcr.io \
    --docker-username=<your-github-username> \
    --docker-password="$(gh auth token)"
  ```

  A GitHub token with `write:packages` scope (or `read:packages` for a
  pull-only credential) works. Skip this if the secret already exists in
  the namespace.
- **Required `secrets.*` Helm values.** `values.staging.yaml` has no
  `secrets:` block, so `--set` flags for these four values are required on
  every `helm upgrade` (see step 3 below) — the backend's startup lifespan
  fails fast (`KeyError`/`RuntimeError`, Phase 5 Task 14) without them, and
  `secrets.databaseUrl` is enforced with Helm's `required` so the chart
  itself now refuses to render/deploy without it:
  - `secrets.databaseUrl` — Postgres connection string
  - `secrets.oidcIssuer` — OIDC issuer URL
  - `secrets.oidcAudience` — OIDC audience
  - `secrets.oidcJwksUrl` **or** `secrets.oidcJwksStatic` — one of the two,
    for JWKS key resolution

  `values.staging.yaml` now sets `zitadel.enabled: true`, so every
  `helm upgrade` documented below also requires:
  - `zitadel.masterkey` — exactly 32 characters. **Generate this once and
    never regenerate it.** Zitadel cannot decrypt data encrypted under a
    previous masterkey, so passing a different value on a later deploy
    permanently locks the existing instance out of its own data. Before
    generating a new one, check whether it's already stored: the chart
    writes it into the `<release>-opentourney-zitadel-secrets` Secret's
    `ZITADEL_MASTERKEY` key —
    `kubectl -n opentourney-staging get secret <release>-opentourney-zitadel-secrets -o jsonpath='{.data.ZITADEL_MASTERKEY}' | base64 -d`
    — and reuse that value rather than minting a fresh one.
  - `zitadel.firstInstance.adminPassword` — Zitadel's complexity policy
    (8+ chars, upper, lower, digit, symbol). Only consumed by Zitadel's
    one-time FirstInstance bootstrap, so it matters far less on repeat
    deploys than the masterkey does, but the chart's `required` guard still
    demands a value on every render since the whole `zitadel:` block is
    unconditionally templated when `zitadel.enabled=true`.

### Namespace & values

- Namespace: `opentourney-staging`
- Helm values: `charts/opentourney/values.staging.yaml` (layered on top of
  `charts/opentourney/values.yaml`)
- kubectl context: `mcgee-local` (or `mcgee-remote` if off-network and
  `mcgee-local` times out)
- Public URL: TBD — no Cloudflare Tunnel hostname is assigned yet. Until one
  exists, reach the deployment via `kubectl port-forward`.

### Deploy workflow

1. **Build images locally from the feature branch**, targeting the cluster's
   architecture:

   ```bash
   docker build --platform linux/amd64 -t ghcr.io/badconfigstudios/opentourney/backend:<tag> -f backend/Dockerfile.prod ./backend
   docker build --platform linux/amd64 -t ghcr.io/badconfigstudios/opentourney/frontend:<tag> -f frontend/Dockerfile.prod ./frontend
   docker build --platform linux/amd64 -t ghcr.io/badconfigstudios/opentourney/docs:<tag> -f docs/Dockerfile.docs .
   ```

2. **Push to GHCR**:

   ```bash
   docker push ghcr.io/badconfigstudios/opentourney/backend:<tag>
   docker push ghcr.io/badconfigstudios/opentourney/frontend:<tag>
   docker push ghcr.io/badconfigstudios/opentourney/docs:<tag>
   ```

3. **Deploy/update the release**:

   ```bash
   helm upgrade --install opentourney-staging charts/opentourney \
     --namespace opentourney-staging --create-namespace \
     -f charts/opentourney/values.staging.yaml \
     --set backend.image.tag=<tag> \
     --set frontend.image.tag=<tag> \
     --set docs.image.tag=<tag> \
     --set-string secrets.databaseUrl=<database-url> \
     --set-string secrets.oidcIssuer=<zitadel-issuer> \
     --set-string secrets.oidcAudience=<client-id-from-bootstrap-log> \
     --set-string secrets.oidcJwksUrl=<zitadel-issuer>/oauth/v2/keys \
     --set-string zitadel.masterkey=<32-char-masterkey> \
     --set-string zitadel.firstInstance.adminPassword=<admin-password>
   ```

   `secrets.databaseUrl`, `secrets.oidcIssuer`, and `secrets.oidcAudience`
   are required (see Prerequisites above) — the chart's `required` guard on
   `secrets.databaseUrl` makes an unset/typo'd value fail the `helm upgrade`
   itself rather than silently deploying a broken release.

   `<zitadel-issuer>` is `.Values.zitadel.externalDomain` prefixed with its
   scheme and suffixed with its port (e.g.
   `http://zitadel.opentourney-staging.svc.cluster.local:8080`) — in-cluster
   only, since no public hostname exists yet (see Namespace & values below).
   `<zitadel-issuer-hostname>` used in the steps below is just the bare
   hostname part of this value (e.g. `zitadel.opentourney-staging.svc.cluster.local`).
   `<client-id-from-bootstrap-log>` comes from the Zitadel bootstrap
   sidecar's own log line, `application 'opentourney-cli' client_id=...`
   (`kubectl -n opentourney-staging logs deploy/opentourney-staging-opentourney-zitadel -c bootstrap`).

   **Ordering gotcha:** on a *fresh* Zitadel stand-up, the OIDC client
   doesn't exist until after Zitadel's pod comes up and its bootstrap sidecar
   runs, so `secrets.oidcAudience` can't be the correct real value on the very
   first `helm upgrade` in a new namespace. Pass any placeholder string for
   that first deploy (it's not Helm-`required`-enforced like
   `secrets.databaseUrl`, so the deploy won't fail); the backend only needs to
   validate it once Zitadel itself is running anyway. After the first deploy
   succeeds, read the logged `client_id`, then `helm upgrade` again with
   `secrets.oidcAudience` set correctly. Because `get_or_create_application()`
   is idempotent, ordinary re-deploys against an already-bootstrapped
   instance never hit this — only a full teardown/rebuild does. `zitadel.masterkey` and
   `zitadel.firstInstance.adminPassword` are likewise required now that
   `values.staging.yaml` sets `zitadel.enabled: true` — see the Prerequisites
   note above on `zitadel.masterkey` before ever changing this value; reuse
   the already-stored one, don't regenerate.

   `zitadel.enabled` defaults to `true` via `values.staging.yaml`'s own
   `-f` layer above, so it doesn't need a `--set` — but this also means
   running this same command with `zitadel.enabled` accidentally overridden
   to `false` (e.g. a stray `--set zitadel.enabled=false`) deletes the
   Zitadel Deployment/Service/Secret and drops the `zitadel` Postgres user,
   since the whole component is guarded by a single `{{- if .Values.zitadel.enabled }}`.

   For a quick image-only iteration once the release already exists, use
   `kubectl set image` instead of a full `helm upgrade`:

   ```bash
   kubectl --context mcgee-local -n opentourney-staging set image \
     deployment/opentourney-staging-opentourney-backend backend=ghcr.io/badconfigstudios/opentourney/backend:<tag>
   kubectl --context mcgee-local -n opentourney-staging rollout status deployment/opentourney-staging-opentourney-backend
   ```

### Verifying a real Zitadel login

Confirms the backend actually accepts a Zitadel-issued token end to end
(role claim, `source_system` claim, signature/issuer/audience validation) —
not just that the Helm secret values look right.

1. Port-forward Zitadel:

   ```bash
   kubectl --context mcgee-local -n opentourney-staging port-forward svc/zitadel 8080:8080
   ```

2. Zitadel checks the request `Host` header against `ZITADEL_EXTERNALDOMAIN`
   (anti-DNS-rebinding) and 404s otherwise. Add a temporary `/etc/hosts`
   entry mapping that hostname to `127.0.0.1` (or pass
   `curl --resolve <hostname>:8080:127.0.0.1` on every request below).

3. Generate a PKCE pair and open the authorize URL in a browser:

   ```bash
   python3 -c "
   import base64, hashlib, secrets
   verifier = secrets.token_urlsafe(64)
   challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
   print('verifier:', verifier)
   print('challenge:', challenge)
   "
   ```

   ```
   http://<zitadel-issuer-hostname>:8080/oauth/v2/authorize
     ?client_id=<client-id-from-bootstrap-log>
     &redirect_uri=http://localhost:8765/callback
     &response_type=code
     &scope=openid profile
     &code_challenge=<challenge>
     &code_challenge_method=S256
   ```

   Log in as `organizer@staging.local` with the password the bootstrap
   sidecar logged at creation time.

4. The browser redirects to `http://localhost:8765/callback?code=...`
   (404 in the browser — nothing is listening, that's expected). Copy the
   `code` value out of the address bar.

5. Exchange it for a token:

   ```bash
   curl -s -X POST http://<zitadel-issuer-hostname>:8080/oauth/v2/token \
     -H 'Host: <zitadel-issuer-hostname>' \
     -d grant_type=authorization_code \
     -d code=<code-from-step-4> \
     -d redirect_uri=http://localhost:8765/callback \
     -d client_id=<client-id-from-bootstrap-log> \
     -d code_verifier=<verifier-from-step-3>
   ```

   Expected: a JSON body containing `access_token`.

6. Port-forward the backend service (no public hostname yet):

   ```bash
   kubectl --context mcgee-local -n opentourney-staging port-forward svc/backend 8000:8000
   ```

7. Call the backend with it:

   ```bash
   curl -s -H "Authorization: Bearer <access_token>" \
     http://localhost:8000/events
   ```

   Expected: `200`, not `401`. A `401` here most often means
   `secrets.oidcAudience` doesn't match the token's `aud` (re-check the
   bootstrap log's `client_id`), or `secrets.oidcIssuer`/`oidcJwksUrl` are
   pointed at the wrong host.

**Troubleshooting the authorize call:** if Zitadel rejects the redirect URI
outright (400 on step 3, before any login page renders), the client likely
needs `"devMode": true` added to Task 1's `get_or_create_application()`
request body — Zitadel's default posture requires HTTPS redirect URIs for
non-loopback apps, and this deployment (`ZITADEL_EXTERNALSECURE=false`)
runs entirely over HTTP. Add the field, re-run the bootstrap Job/pod
restart, and retry.

### Known gotchas

- New GHCR packages need an explicit namespaced pull secret (see
  Prerequisites above) — confirmed via a real staging deploy that neither
  the cluster's node-level registry config nor the default ServiceAccount
  cover packages the first time they're pushed, regardless of the package's
  visibility setting (`internal` vs `private` made no observed difference).
- Percona PG Operator v3 requires an explicit `spec.backups.pgbackrest` section
  even when backups aren't meaningfully needed for a disposable staging
  environment — omitting it causes the CRD to reject the resource.
- Passwords with special characters need URL-encoding in `DATABASE_URL` once
  the backend actually consumes one (Phase 3+); Alembic's configparser also
  needs `%` escaped as `%%`.
