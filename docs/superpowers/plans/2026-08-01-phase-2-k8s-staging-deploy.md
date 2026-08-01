# Phase 2 — Kubernetes Staging Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OpenTourney's backend and frontend deployable to a k3s staging namespace via a Helm chart (Deployments/Services + Percona PostgreSQL Operator cluster), with a CD workflow that builds and pushes production images on `badconfig-runners`.

**Architecture:** Mirror the proven pattern from the sibling `limitless-organizer-tracker` repo: a single Helm chart parameterized by `values.yaml` (production defaults) layered with `values.staging.yaml` (staging overrides), production-only Dockerfiles (`Dockerfile.prod`) separate from the existing dev Dockerfiles, and a GitHub Actions workflow that builds/pushes images to GHCR on merge to `main`. Staging deploys are a **manual** `helm upgrade` / `kubectl set image` workflow (not GitOps) run as a pre-merge gate — this matches the sibling project's `docs/deployment/staging.md` pattern exactly, and keeps production Fleet GitOps out of scope (no production release exists yet; that's MVP1's `v0.1.0` cut in Phase 8).

**Tech Stack:** Helm 3, Percona PG Operator v3 CRD (`pgv2.percona.com/v2`), Docker multi-stage builds, nginx (frontend static serving), GitHub Actions on `badconfig-runners`, GHCR (`ghcr.io/badconfigstudios/opentourney/*`).

## Global Constraints

- Traces to `REQUIREMENTS.md` FR5 (Helm chart: backend + frontend Deployments/Services, Percona PG Operator, deployable to k3s staging namespace) and FR6 (CD workflow via `badconfig-runners`).
- No Redis, no Celery/worker, no docs-site image, no Secret/ConfigMap templates — none are needed yet. OpenTourney's backend has zero configurable env vars and zero DB usage today (`backend/app/main.py` is `/healthz` only; domain model + DB wiring is Phase 3). Adding them now would be speculative config with nothing to validate. **Do not add these** — this is a deliberate YAGNI cut, not an oversight.
- No production Fleet GitOps bundle (`fleet.yaml`) and no Ingress template — neither is required by FR5 (which lists only Deployments/Services + Percona), no domain is assigned yet, and REQUIREMENTS.md scopes Phase 2 to "staging namespace" only. `values.yaml` (production-shaped defaults) is written for chart completeness but is not deployed anywhere in this phase. Do not invent a public URL/hostname for OpenTourney — an Ingress resource with no real host to point at is dead weight, not "chart completeness." Revisit when a production deployment is actually scoped (Phase 8+).
- Percona PG Operator v3 CRD requires an explicit `spec.backups.pgbackrest` section even when backups aren't meaningfully needed (staging) — known gotcha from the sibling repo's `docs/deployment/staging.md`. Every `PerconaPGCluster` resource must include it.
- Image registry: `ghcr.io/badconfigstudios/opentourney/backend` and `.../frontend` (lowercase, hardcoded — do not template `${{ github.repository }}` directly, since the GitHub-reported casing is `BadConfigStudios/OpenTourney` and GHCR image paths must be lowercase).
- CD workflow (`build-push.yml`) triggers only on `push` to `main`/`v*` tags — **not** on `pull_request`. `ci.yml`'s existing `docker-build` job already validates both Dockerfiles build on every PR without pushing; duplicating a push-triggering build on every PR would push throwaway PR-tagged images to GHCR for no benefit.
- No unit-test framework applies to Helm/Docker/YAML infra config. The equivalent RED/GREEN cycle here is: run the verification command first and confirm it fails/errors (file doesn't exist yet), then create the file and confirm the same command passes. Every task uses `helm lint`, `helm template`, `docker build`, or a YAML parse check as its test.

---

### Task 1: Backend production Dockerfile

**Files:**
- Create: `backend/Dockerfile.prod`
- Test: none (verified via `docker build`, see steps)

**Interfaces:**
- Consumes: `backend/pyproject.toml` (existing, unchanged), `backend/app/` (existing, unchanged)
- Produces: a `opentourney-backend:test` image importable by later chart/deploy work as `ghcr.io/badconfigstudios/opentourney/backend`

- [ ] **Step 1: Confirm no prod Dockerfile exists yet (RED)**

Run: `test -f backend/Dockerfile.prod && echo EXISTS || echo MISSING`
Expected: `MISSING`

- [ ] **Step 2: Write `backend/Dockerfile.prod`**

```dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

This mirrors the sibling repo's `backend/Dockerfile.prod` layering trick: `pip install .` runs against just `pyproject.toml` first (installs `fastapi`, `uvicorn`, `pydantic` as a cacheable layer with no dev extras), then `COPY . .` places the actual `app/` source on disk. Uvicorn imports `app.main:app` from the working directory at runtime, not from a wheel — no editable install, no entrypoint script (no Alembic migrations exist yet; that lands with the domain model in Phase 3).

- [ ] **Step 3: Build the image (GREEN)**

Run: `docker build -t opentourney-backend:test -f backend/Dockerfile.prod ./backend`
Expected: build succeeds, ends with `naming to docker.io/library/opentourney-backend:test`

- [ ] **Step 4: Smoke-test the container serves `/healthz`**

Run:
```bash
docker run -d --rm -p 18000:8000 --name ot-backend-test opentourney-backend:test
sleep 2
curl -sf http://localhost:18000/healthz
docker stop ot-backend-test
```
Expected: `{"status":"ok"}`, container stops cleanly

- [ ] **Step 5: Commit**

```bash
git add backend/Dockerfile.prod
git commit -m "feat(deploy): add backend production Dockerfile"
```

---

### Task 2: Frontend production Dockerfile + nginx

**Files:**
- Create: `frontend/Dockerfile.prod`
- Create: `frontend/nginx.conf`
- Test: none (verified via `docker build`, see steps)

**Interfaces:**
- Consumes: `frontend/package.json` (existing, has `build` script: `tsc --noEmit && vite build`), `frontend/src/` (existing)
- Produces: a `opentourney-frontend:test` image importable by later chart/deploy work as `ghcr.io/badconfigstudios/opentourney/frontend`

- [ ] **Step 1: Confirm no prod Dockerfile exists yet (RED)**

Run: `test -f frontend/Dockerfile.prod && echo EXISTS || echo MISSING`
Expected: `MISSING`

- [ ] **Step 2: Write `frontend/nginx.conf`**

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

Static SPA serving only — no `/api`/`/healthz` proxy rules. The frontend doesn't call the backend yet (it's a placeholder `<h1>OpenTourney</h1>`, see `frontend/src/App.tsx`), and Kubernetes readiness/liveness probes hit the backend Service directly, not through the frontend. Add proxy rules when the frontend actually makes API calls (Phase 5+).

- [ ] **Step 3: Write `frontend/Dockerfile.prod`**

```dockerfile
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
```

- [ ] **Step 4: Build the image (GREEN)**

Run: `docker build -t opentourney-frontend:test -f frontend/Dockerfile.prod ./frontend`
Expected: build succeeds (runs `tsc --noEmit && vite build` inside the build stage), ends with `naming to docker.io/library/opentourney-frontend:test`

- [ ] **Step 5: Smoke-test the container serves the SPA**

Run:
```bash
docker run -d --rm -p 18080:80 --name ot-frontend-test opentourney-frontend:test
sleep 1
curl -sf http://localhost:18080/ | grep -o '<div id="root">'
docker stop ot-frontend-test
```
Expected: matches `<div id="root">` (Vite's default mount point), container stops cleanly

- [ ] **Step 6: Commit**

```bash
git add frontend/Dockerfile.prod frontend/nginx.conf
git commit -m "feat(deploy): add frontend production Dockerfile + nginx config"
```

---

### Task 3: Helm chart skeleton — Chart.yaml, helpers, values

**Files:**
- Create: `charts/opentourney/Chart.yaml`
- Create: `charts/opentourney/templates/_helpers.tpl`
- Create: `charts/opentourney/values.yaml`
- Create: `charts/opentourney/values.staging.yaml`
- Test: none yet (chart has no templates to render until Task 4-6; verified via `helm lint` once templates exist — this task just lays the values contract every later template reads from)

**Interfaces:**
- Produces: Helm values contract consumed by Tasks 4-6:
  - `.Values.backend.image.{repository,tag,pullPolicy}`, `.Values.backend.replicas`, `.Values.backend.port`
  - `.Values.frontend.image.{repository,tag,pullPolicy}`, `.Values.frontend.replicas`, `.Values.frontend.port`
  - `.Values.percona.{enabled,clusterName,pgVersion,storageSize,backupStorageSize}`
  - Template helpers `ot.fullname` and `ot.labels`

- [ ] **Step 1: Confirm chart directory doesn't exist yet (RED)**

Run: `test -d charts/opentourney && echo EXISTS || echo MISSING`
Expected: `MISSING`

- [ ] **Step 2: Write `charts/opentourney/Chart.yaml`**

```yaml
apiVersion: v2
name: opentourney
description: OpenTourney — backend, frontend, and Percona PostgreSQL
type: application
version: 0.1.0
appVersion: "0.1.0"
```

- [ ] **Step 3: Write `charts/opentourney/templates/_helpers.tpl`**

```
{{- define "ot.fullname" -}}
{{ .Release.Name }}-{{ .Chart.Name | trunc 40 }}
{{- end -}}

{{- define "ot.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
```

- [ ] **Step 4: Write `charts/opentourney/values.yaml`** (production-shaped defaults; not deployed this phase)

```yaml
namespace: opentourney

backend:
  image:
    repository: ghcr.io/badconfigstudios/opentourney/backend
    tag: latest
    pullPolicy: Always
  replicas: 1
  port: 8000

frontend:
  image:
    repository: ghcr.io/badconfigstudios/opentourney/frontend
    tag: latest
    pullPolicy: Always
  replicas: 1
  port: 80

# Percona PostgreSQL Operator CRD
percona:
  enabled: true
  clusterName: opentourney-pg
  pgVersion: "16"
  storageSize: 5Gi
  backupStorageSize: 5Gi
```

- [ ] **Step 5: Write `charts/opentourney/values.staging.yaml`**

```yaml
namespace: opentourney-staging

backend:
  image:
    tag: latest
    pullPolicy: Always
  replicas: 1

frontend:
  image:
    tag: latest
    pullPolicy: Always
  replicas: 1

percona:
  enabled: true
  clusterName: opentourney-staging-pg
  pgVersion: "16"
  storageSize: 1Gi
  backupStorageSize: 1Gi
```

- [ ] **Step 6: Commit**

```bash
git add charts/opentourney/Chart.yaml charts/opentourney/templates/_helpers.tpl charts/opentourney/values.yaml charts/opentourney/values.staging.yaml
git commit -m "feat(deploy): scaffold opentourney Helm chart values contract"
```

---

### Task 4: Backend Deployment + Service templates

**Files:**
- Create: `charts/opentourney/templates/deployment-backend.yaml`
- Create: `charts/opentourney/templates/service-backend.yaml`

**Interfaces:**
- Consumes: `ot.fullname`, `ot.labels` (Task 3), `.Values.backend.*` (Task 3)
- Produces: a `backend` Service (flat name, no release prefix — same-namespace-only addressing, matches the sibling chart's pattern) reachable at `backend:{{ .Values.backend.port }}`

- [ ] **Step 1: Confirm chart has no templates yet (RED)**

Run: `helm lint charts/opentourney 2>&1 | tail -5`
Expected: passes trivially (no templates to render is not an error, but there's nothing to validate yet — this step is a checkpoint, not a real failure)

- [ ] **Step 2: Write `charts/opentourney/templates/deployment-backend.yaml`**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "ot.fullname" . }}-backend
  labels:
    {{- include "ot.labels" . | nindent 4 }}
    app.kubernetes.io/component: backend
spec:
  replicas: {{ .Values.backend.replicas }}
  selector:
    matchLabels:
      app.kubernetes.io/component: backend
      app.kubernetes.io/instance: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/component: backend
        app.kubernetes.io/instance: {{ .Release.Name }}
    spec:
      containers:
        - name: backend
          image: "{{ .Values.backend.image.repository }}:{{ .Values.backend.image.tag }}"
          imagePullPolicy: {{ .Values.backend.image.pullPolicy }}
          ports:
            - containerPort: {{ .Values.backend.port }}
          readinessProbe:
            httpGet:
              path: /healthz
              port: {{ .Values.backend.port }}
            initialDelaySeconds: 10
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /healthz
              port: {{ .Values.backend.port }}
            initialDelaySeconds: 15
            periodSeconds: 30
```

- [ ] **Step 3: Write `charts/opentourney/templates/service-backend.yaml`**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: backend
  labels:
    {{- include "ot.labels" . | nindent 4 }}
    app.kubernetes.io/component: backend
spec:
  selector:
    app.kubernetes.io/component: backend
    app.kubernetes.io/instance: {{ .Release.Name }}
  ports:
    - port: {{ .Values.backend.port }}
      targetPort: {{ .Values.backend.port }}
```

- [ ] **Step 4: Render and validate (GREEN)**

Run: `helm template opentourney charts/opentourney -f charts/opentourney/values.staging.yaml | grep -A2 "kind: Deployment"`
Expected: shows the backend Deployment with image `ghcr.io/badconfigstudios/opentourney/backend:latest`, no template errors

Run: `helm lint charts/opentourney -f charts/opentourney/values.staging.yaml`
Expected: `0 chart(s) failed`

- [ ] **Step 5: Commit**

```bash
git add charts/opentourney/templates/deployment-backend.yaml charts/opentourney/templates/service-backend.yaml
git commit -m "feat(deploy): add backend Deployment and Service templates"
```

---

### Task 5: Frontend Deployment + Service templates

**Files:**
- Create: `charts/opentourney/templates/deployment-frontend.yaml`
- Create: `charts/opentourney/templates/service-frontend.yaml`

**Interfaces:**
- Consumes: `ot.fullname`, `ot.labels` (Task 3), `.Values.frontend.*` (Task 3)
- Produces: a `frontend` Service (flat name) reachable at `frontend:80`

- [ ] **Step 1: Confirm frontend templates don't exist yet (RED)**

Run: `test -f charts/opentourney/templates/deployment-frontend.yaml && echo EXISTS || echo MISSING`
Expected: `MISSING`

- [ ] **Step 2: Write `charts/opentourney/templates/deployment-frontend.yaml`**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "ot.fullname" . }}-frontend
  labels:
    {{- include "ot.labels" . | nindent 4 }}
    app.kubernetes.io/component: frontend
spec:
  replicas: {{ .Values.frontend.replicas }}
  selector:
    matchLabels:
      app.kubernetes.io/component: frontend
      app.kubernetes.io/instance: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/component: frontend
        app.kubernetes.io/instance: {{ .Release.Name }}
    spec:
      containers:
        - name: frontend
          image: "{{ .Values.frontend.image.repository }}:{{ .Values.frontend.image.tag }}"
          imagePullPolicy: {{ .Values.frontend.image.pullPolicy }}
          ports:
            - containerPort: {{ .Values.frontend.port }}
          readinessProbe:
            httpGet:
              path: /
              port: {{ .Values.frontend.port }}
            initialDelaySeconds: 5
            periodSeconds: 10
```

- [ ] **Step 3: Write `charts/opentourney/templates/service-frontend.yaml`**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: frontend
  labels:
    {{- include "ot.labels" . | nindent 4 }}
    app.kubernetes.io/component: frontend
spec:
  selector:
    app.kubernetes.io/component: frontend
    app.kubernetes.io/instance: {{ .Release.Name }}
  ports:
    - port: 80
      targetPort: {{ .Values.frontend.port }}
```

- [ ] **Step 4: Render and validate (GREEN)**

Run: `helm template opentourney charts/opentourney -f charts/opentourney/values.staging.yaml | grep -A2 "kind: Deployment"`
Expected: shows both backend and frontend Deployments, no template errors

Run: `helm lint charts/opentourney -f charts/opentourney/values.staging.yaml`
Expected: `0 chart(s) failed`

- [ ] **Step 5: Commit**

```bash
git add charts/opentourney/templates/deployment-frontend.yaml charts/opentourney/templates/service-frontend.yaml
git commit -m "feat(deploy): add frontend Deployment and Service templates"
```

---

### Task 6: Percona PGCluster template

**Files:**
- Create: `charts/opentourney/templates/percona-pgcluster.yaml`

**Interfaces:**
- Consumes: `ot.labels` (Task 3), `.Values.percona.*` (Task 3)
- Produces: a `PerconaPGCluster` resource (`pgv2.percona.com/v2`) named `{{ .Values.percona.clusterName }}`, provisioning a database and user both named `opentourney` — ready for Phase 3's Alembic wiring to consume via the operator's auto-generated `<clusterName>-pguser-opentourney` Secret

- [ ] **Step 1: Confirm the template doesn't exist yet (RED)**

Run: `test -f charts/opentourney/templates/percona-pgcluster.yaml && echo EXISTS || echo MISSING`
Expected: `MISSING`

- [ ] **Step 2: Write `charts/opentourney/templates/percona-pgcluster.yaml`**

```yaml
{{- if .Values.percona.enabled }}
apiVersion: pgv2.percona.com/v2
kind: PerconaPGCluster
metadata:
  name: {{ .Values.percona.clusterName }}
  labels:
    {{- include "ot.labels" . | nindent 4 }}
spec:
  crVersion: "3.0.0"
  image: percona/percona-distribution-postgresql:16-ubi8
  postgresVersion: {{ .Values.percona.pgVersion | int }}
  instances:
    - name: instance1
      replicas: 1
      dataVolumeClaimSpec:
        accessModes:
          - ReadWriteOnce
        resources:
          requests:
            storage: {{ .Values.percona.storageSize }}
  backups:
    pgbackrest:
      image: percona/percona-pgbackrest:2.58.0
      repos:
        - name: repo1
          volume:
            volumeClaimSpec:
              accessModes:
                - ReadWriteOnce
              resources:
                requests:
                  storage: {{ .Values.percona.backupStorageSize }}
  users:
    - name: opentourney
      databases:
        - opentourney
      options: "SUPERUSER"
{{- end }}
```

Note: `spec.backups.pgbackrest` is required by the Percona v3 CRD even in staging where backups aren't meaningfully needed — omitting it causes the CRD to reject the resource (known gotcha, see `~/.claude/projects/.../memory/project_deployment_target.md`).

- [ ] **Step 3: Render and validate (GREEN)**

Run: `helm template opentourney charts/opentourney -f charts/opentourney/values.staging.yaml | grep -A5 "kind: PerconaPGCluster"`
Expected: shows `name: opentourney-staging-pg`, `storage: 1Gi` (from `values.staging.yaml`), no template errors

Run: `helm lint charts/opentourney -f charts/opentourney/values.staging.yaml`
Expected: `0 chart(s) failed`

- [ ] **Step 4: Commit**

```bash
git add charts/opentourney/templates/percona-pgcluster.yaml
git commit -m "feat(deploy): add Percona PGCluster template"
```

---

### Task 7: CD workflow — build & push images

**Files:**
- Create: `.github/workflows/build-push.yml`

**Interfaces:**
- Consumes: `backend/Dockerfile.prod` (Task 1), `frontend/Dockerfile.prod` (Task 2)
- Produces: `ghcr.io/badconfigstudios/opentourney/backend:latest` and `ghcr.io/badconfigstudios/opentourney/frontend:latest` on every push to `main`; semver + sha tags on `v*` tags

- [ ] **Step 1: Confirm the workflow doesn't exist yet (RED)**

Run: `test -f .github/workflows/build-push.yml && echo EXISTS || echo MISSING`
Expected: `MISSING`

- [ ] **Step 2: Write `.github/workflows/build-push.yml`**

```yaml
name: Build & Push Images

on:
  push:
    branches: [main]
    tags: ["v*"]
    paths:
      - "backend/**"
      - "frontend/**"
      - ".github/workflows/build-push.yml"

env:
  REGISTRY: ghcr.io
  BACKEND_IMAGE: ghcr.io/badconfigstudios/opentourney/backend
  FRONTEND_IMAGE: ghcr.io/badconfigstudios/opentourney/frontend

jobs:
  build-backend:
    runs-on: badconfig-runners
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ${{ env.BACKEND_IMAGE }}
          tags: |
            type=semver,pattern={{version}}
            type=sha
            type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' }}

      - uses: docker/build-push-action@v6
        with:
          context: ./backend
          file: ./backend/Dockerfile.prod
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}

  build-frontend:
    runs-on: badconfig-runners
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ${{ env.FRONTEND_IMAGE }}
          tags: |
            type=semver,pattern={{version}}
            type=sha
            type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' }}

      - uses: docker/build-push-action@v6
        with:
          context: ./frontend
          file: ./frontend/Dockerfile.prod
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

- [ ] **Step 3: Validate YAML syntax (GREEN)**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/build-push.yml'))" && echo VALID`
Expected: `VALID`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/build-push.yml
git commit -m "feat(deploy): add CD workflow to build and push production images"
```

---

### Task 8: Staging deployment docs

**Files:**
- Create: `DEVELOPMENT.md`

**Interfaces:**
- Consumes: namespace/release names from `charts/opentourney/values.staging.yaml` (Task 3), image names from Task 7
- Produces: none (documentation only)

- [ ] **Step 1: Confirm the doc doesn't exist yet (RED)**

Run: `test -f DEVELOPMENT.md && echo EXISTS || echo MISSING`
Expected: `MISSING`

- [ ] **Step 2: Write `DEVELOPMENT.md`**

```markdown
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
```

- [ ] **Step 3: Verify the doc is present and non-empty**

Run: `wc -l DEVELOPMENT.md`
Expected: a non-zero line count (the file exists and has content)

- [ ] **Step 4: Commit**

```bash
git add DEVELOPMENT.md
git commit -m "docs: add staging deployment workflow"
```

---

### Task 9: Full-chart verification

**Files:**
- None created — this task only runs verification across everything from Tasks 3-6.

**Interfaces:**
- Consumes: the complete chart from Tasks 3-6
- Produces: nothing (verification-only task, no commit)

- [ ] **Step 1: Lint the full chart against both values files**

Run:
```bash
helm lint charts/opentourney -f charts/opentourney/values.yaml
helm lint charts/opentourney -f charts/opentourney/values.staging.yaml
```
Expected: `0 chart(s) failed` for both

- [ ] **Step 2: Render the full staging manifest and eyeball resource count**

Run: `helm template opentourney-staging charts/opentourney -f charts/opentourney/values.staging.yaml | grep -E "^kind:"`
Expected: exactly `Deployment` (x2), `Service` (x2), `PerconaPGCluster` (x1) — no `Ingress`/`Secret`/`ConfigMap` (none defined, per Global Constraints)

- [ ] **Step 3: Confirm rendered manifests are valid Kubernetes YAML**

Run: `helm template opentourney-staging charts/opentourney -f charts/opentourney/values.staging.yaml | python3 -c "import sys, yaml; docs = list(yaml.safe_load_all(sys.stdin)); print(f'{len(docs)} documents parsed OK')"`
Expected: `5 documents parsed OK`

- [ ] **Step 4: Re-run backend and frontend Docker builds to confirm nothing regressed**

Run:
```bash
docker build -t opentourney-backend:test -f backend/Dockerfile.prod ./backend
docker build -t opentourney-frontend:test -f frontend/Dockerfile.prod ./frontend
```
Expected: both succeed

This task has no commit — it's a checkpoint before opening the PR, not a code change.

---

## Post-plan: not part of any task above

- Actual staging deployment (running the Task 8 workflow against the real cube
  cluster) is **manual verification**, done after this plan's tasks are
  complete and before the PR is merged, per the mandatory pre-merge gate. It
  is not a plan task because it doesn't produce a commit — see the
  `DEVELOPMENT.md` workflow for exact commands.
- Production Fleet GitOps bundle and Ingress template: explicitly out of scope
  (see Global Constraints) — revisit once a production deployment is actually
  scoped (Phase 8+).
