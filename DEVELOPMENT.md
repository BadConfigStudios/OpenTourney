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
- **GHCR pull credentials for `opentourney/backend` and `opentourney/frontend`.**
  Neither package exists yet — GHCR creates them private by default on first
  push. Check whether the target namespace's default ServiceAccount already
  has a working pull credential:

  ```bash
  kubectl -n opentourney-staging get sa default -o yaml
  ```

  and look for `imagePullSecrets`. Also check for a node-level registry
  credential (e.g. k3s's `/etc/rancher/k3s/registries.yaml`). If neither is
  present, create a pull secret and pass it to Helm via
  `--set imagePullSecrets[0].name=<secret-name>` (see
  `charts/opentourney/values.yaml`'s `imagePullSecrets` key).

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
     --set frontend.image.tag=<tag>
   ```

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

- Percona PG Operator v3 requires an explicit `spec.backups.pgbackrest` section
  even when backups aren't meaningfully needed for a disposable staging
  environment — omitting it causes the CRD to reject the resource.
- Passwords with special characters need URL-encoding in `DATABASE_URL` once
  the backend actually consumes one (Phase 3+); Alembic's configparser also
  needs `%` escaped as `%%`.
