# Development & Deployment

## Local development

See `backend/` and `frontend/` for their own dev setup (`pip install -e ".[dev]"` /
`npm install`). Both run standalone via their existing (non-prod) `Dockerfile`s.

## Staging deployment

Staging deploys the current feature branch to the cube cluster (k3s on openSUSE
MicroOS) **before** merging to `main`, so changes are validated against a real
cluster and real Postgres prior to merge. This is a manual `helm` workflow —
staging is not managed by Fleet/GitOps (no production release exists yet; that
lands with the `v0.1.0` cut in Phase 8).

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
   ```

2. **Push to GHCR**:

   ```bash
   docker push ghcr.io/badconfigstudios/opentourney/backend:<tag>
   docker push ghcr.io/badconfigstudios/opentourney/frontend:<tag>
   ```

3. **Deploy/update the release**:

   ```bash
   helm upgrade --install opentourney-staging charts/opentourney \
     --namespace opentourney-staging --create-namespace \
     -f charts/opentourney/values.staging.yaml \
     --set backend.image.tag=<tag> \
     --set frontend.image.tag=<tag> \
     --set-string secrets.databaseUrl=<database-url> \
     --set-string secrets.oidcIssuer=<oidc-issuer> \
     --set-string secrets.oidcAudience=<oidc-audience> \
     --set-string secrets.oidcJwksStatic=<oidc-jwks-static-json>
   ```

   `secrets.databaseUrl`, `secrets.oidcIssuer`, and `secrets.oidcAudience`
   are required (see Prerequisites above) — the chart's `required` guard on
   `secrets.databaseUrl` makes an unset/typo'd value fail the `helm upgrade`
   itself rather than silently deploying a broken release. Use
   `--set-string secrets.oidcJwksUrl=<oidc-jwks-url>` instead of
   `secrets.oidcJwksStatic` if the issuer's JWKS should be fetched live
   rather than pinned.

   For a quick image-only iteration once the release already exists, use
   `kubectl set image` instead of a full `helm upgrade`:

   ```bash
   kubectl --context mcgee-local -n opentourney-staging set image \
     deployment/opentourney-staging-opentourney-backend backend=ghcr.io/badconfigstudios/opentourney/backend:<tag>
   kubectl --context mcgee-local -n opentourney-staging rollout status deployment/opentourney-staging-opentourney-backend
   ```

4. **Verify** via `kubectl port-forward` (no public hostname yet):

   ```bash
   kubectl --context mcgee-local -n opentourney-staging port-forward svc/backend 8000:8000
   curl http://localhost:8000/healthz
   ```

5. **Only then** open/merge the PR to `main`.

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
