# Phase 14 — Zitadel Broker Infra Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a self-hosted Zitadel instance into `opentourney-staging` as an optional `charts/opentourney` component, reusing the existing Percona Postgres cluster, and bootstrap it with an OpenTourney project, 3 roles (organizer/scorekeeper/player), and 3 test human users whose tokens carry a flat `roles` claim matching what `identity_from_claims` (`backend/app/auth/identity.py`) already expects.

**Architecture:** A `zitadel.enabled` toggle in `charts/opentourney` (mirrors the existing `percona.enabled` toggle pattern) adds: a new Postgres user/database declared on the existing `PerconaPGCluster` resource, a masterkey Secret, and a Zitadel Deployment running the single-command `start-from-init` (init+setup+start combined — Zitadel's own documented quickstart/staging pattern) with a FirstInstance-bootstrapped machine user whose Personal Access Token (PAT) is written to a shared `emptyDir` volume. A second container in the same Pod (the bootstrap sidecar) reads that PAT and calls Zitadel's Management API to create the OpenTourney project, its 3 roles, 3 test human users, role grants, and a Complement Token Action that adds a flat `roles` claim to issued tokens.

**Tech Stack:** Zitadel `ghcr.io/zitadel/zitadel:v4.17.1` (self-hosted, single Go binary), existing Percona PG Operator v3 cluster (`opentourney-staging-pg`), Python 3 + `requests` for the bootstrap sidecar script (run via `python:3.12-alpine`, no new Dockerfile needed for this phase).

## Global Constraints

- No new namespace, no new Postgres cluster — Zitadel lives in `opentourney-staging`, reuses `opentourney-staging-pg` via its own database/schema (`DECISIONS.md` 2026-08-09, reaffirmed 2026-08-16).
- Zero backend code changes (`RemoteJWKSProvider` already handles any real issuer) — this phase does not touch `backend/app`.
- Chart toggle pattern must mirror `percona.enabled` exactly (`{{- if .Values.zitadel.enabled }}` guarding new templates), per `DECISIONS.md` 2026-08-09.
- Bootstrap must be idempotent — safe to re-run against an already-bootstrapped instance (staging teardown/rebuild scenario, per `DECISIONS.md` 2026-08-16 / the design spec).
- This phase's acceptance is standalone: verified via Zitadel's own login page over `kubectl port-forward`, no OpenTourney frontend involved yet (that's Phase 16).

---

### Task 1: Zitadel's own Postgres database on the existing Percona cluster

**Files:**
- Modify: `charts/opentourney/templates/percona-pgcluster.yaml:33-37`
- Modify: `charts/opentourney/values.yaml`

**Interfaces:**
- Produces: a Kubernetes Secret `opentourney-staging-pg-pguser-zitadel` (Percona Operator's standard naming — mirrors the existing `opentourney-staging-pg-pguser-opentourney` secret already visible via `kubectl get secrets -n opentourney-staging`), containing keys `user`, `password`, `host`, `port`, `dbname` — consumed by Task 2's Zitadel Deployment.

- [ ] **Step 1: Add the `zitadel` Postgres user/database to the existing `PerconaPGCluster` spec**

Edit `charts/opentourney/templates/percona-pgcluster.yaml`, extending the existing `users:` list (currently only the `opentourney` entry):

```yaml
  users:
    - name: opentourney
      databases:
        - opentourney
      options: "SUPERUSER"
    {{- if .Values.zitadel.enabled }}
    - name: zitadel
      databases:
        - zitadel
      options: "SUPERUSER"
    {{- end }}
```

- [ ] **Step 2: Add the `zitadel` values block**

Edit `charts/opentourney/values.yaml`, adding after the existing `secrets:` block:

```yaml
zitadel:
  enabled: false
  image:
    repository: ghcr.io/zitadel/zitadel
    tag: v4.17.1
    pullPolicy: IfNotPresent
  externalDomain: "zitadel.opentourney-staging.svc.cluster.local"
  externalPort: 8080
  firstInstance:
    orgName: "OpenTourney"
    adminUsername: "admin"
    adminPassword: ""
```

`adminPassword` stays empty in the shared chart default — staging supplies it via `--set-string zitadel.firstInstance.adminPassword=...` at deploy time, same pattern as `secrets.databaseUrl`. Zitadel requires it to satisfy: at least 8 characters, including uppercase, lowercase, a number, and a symbol.

- [ ] **Step 3: Render and verify**

Run: `helm template charts/opentourney --set percona.enabled=true --set zitadel.enabled=true --set secrets.databaseUrl=x --set secrets.oidcIssuer=x --set secrets.oidcAudience=x --set secrets.oidcJwksStatic=x -s templates/percona-pgcluster.yaml`
Expected: the rendered `PerconaPGCluster` YAML's `spec.users` list contains both `opentourney` and `zitadel` entries.

Run: `helm lint charts/opentourney`
Expected: `0 chart(s) failed`

- [ ] **Step 4: Commit**

```bash
git add charts/opentourney/templates/percona-pgcluster.yaml charts/opentourney/values.yaml
git commit -m "feat(helm): add zitadel Postgres user/database to the existing Percona cluster"
```

---

### Task 2: Zitadel masterkey Secret + Deployment + Service

**Files:**
- Create: `charts/opentourney/templates/zitadel-secret.yaml`
- Create: `charts/opentourney/templates/zitadel-deployment.yaml`
- Create: `charts/opentourney/templates/zitadel-service.yaml`
- Modify: `charts/opentourney/values.yaml` (add `zitadel.masterkey: ""` alongside the block from Task 1)

**Interfaces:**
- Consumes: `opentourney-staging-pg-pguser-zitadel` Secret (Task 1) for DB connection env vars.
- Produces: a `zitadel` Service in `opentourney-staging` on port 8080, reachable at `zitadel.opentourney-staging.svc.cluster.local:8080` — consumed by Task 3's bootstrap sidecar (in-Pod, via `localhost:8080`) and later by Phase 16's frontend OIDC config.

- [ ] **Step 1: Add the masterkey value**

Edit `charts/opentourney/values.yaml`, adding `masterkey: ""` to the `zitadel:` block from Task 1 (must be exactly 32 characters when supplied — staging passes it via `--set-string zitadel.masterkey=<32-char-random-string>`, generated once with `openssl rand -base64 24 | head -c 32` and stored by the operator, not regenerated per deploy since Zitadel "cannot be changed" after initialization without losing access to encrypted data).

- [ ] **Step 2: Write the masterkey Secret template**

Create `charts/opentourney/templates/zitadel-secret.yaml`:

```yaml
{{- if .Values.zitadel.enabled }}
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "ot.fullname" . }}-zitadel-secrets
  labels:
    {{- include "ot.labels" . | nindent 4 }}
type: Opaque
stringData:
  ZITADEL_MASTERKEY: {{ required "zitadel.masterkey is required when zitadel.enabled=true" .Values.zitadel.masterkey | quote }}
  ZITADEL_FIRSTINSTANCE_ORG_HUMAN_PASSWORD: {{ required "zitadel.firstInstance.adminPassword is required when zitadel.enabled=true" .Values.zitadel.firstInstance.adminPassword | quote }}
{{- end }}
```

- [ ] **Step 3: Write the Deployment template**

Create `charts/opentourney/templates/zitadel-deployment.yaml`:

```yaml
{{- if .Values.zitadel.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "ot.fullname" . }}-zitadel
  labels:
    {{- include "ot.labels" . | nindent 4 }}
    app.kubernetes.io/component: zitadel
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/component: zitadel
      app.kubernetes.io/instance: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/component: zitadel
        app.kubernetes.io/instance: {{ .Release.Name }}
    spec:
      {{- with .Values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      volumes:
        - name: pat
          emptyDir: {}
      containers:
        - name: zitadel
          image: "{{ .Values.zitadel.image.repository }}:{{ .Values.zitadel.image.tag }}"
          imagePullPolicy: {{ .Values.zitadel.image.pullPolicy }}
          args: ["start-from-init", "--masterkeyFromEnv"]
          volumeMounts:
            - name: pat
              mountPath: /pat
          envFrom:
            - secretRef:
                name: {{ include "ot.fullname" . }}-zitadel-secrets
          env:
            - name: ZITADEL_EXTERNALDOMAIN
              value: {{ .Values.zitadel.externalDomain | quote }}
            - name: ZITADEL_EXTERNALPORT
              value: {{ .Values.zitadel.externalPort | quote }}
            - name: ZITADEL_EXTERNALSECURE
              value: "false"
            - name: ZITADEL_TLS_ENABLED
              value: "false"
            - name: ZITADEL_DATABASE_POSTGRES_HOST
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.percona.clusterName }}-pguser-zitadel
                  key: host
            - name: ZITADEL_DATABASE_POSTGRES_PORT
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.percona.clusterName }}-pguser-zitadel
                  key: port
            - name: ZITADEL_DATABASE_POSTGRES_DATABASE
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.percona.clusterName }}-pguser-zitadel
                  key: dbname
            - name: ZITADEL_DATABASE_POSTGRES_USER_USERNAME
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.percona.clusterName }}-pguser-zitadel
                  key: user
            - name: ZITADEL_DATABASE_POSTGRES_USER_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.percona.clusterName }}-pguser-zitadel
                  key: password
            - name: ZITADEL_DATABASE_POSTGRES_USER_SSL_MODE
              value: "disable"
            - name: ZITADEL_DATABASE_POSTGRES_ADMIN_USERNAME
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.percona.clusterName }}-pguser-zitadel
                  key: user
            - name: ZITADEL_DATABASE_POSTGRES_ADMIN_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.percona.clusterName }}-pguser-zitadel
                  key: password
            - name: ZITADEL_DATABASE_POSTGRES_ADMIN_SSL_MODE
              value: "disable"
            - name: ZITADEL_FIRSTINSTANCE_ORG_NAME
              value: {{ .Values.zitadel.firstInstance.orgName | quote }}
            - name: ZITADEL_FIRSTINSTANCE_ORG_HUMAN_USERNAME
              value: {{ .Values.zitadel.firstInstance.adminUsername | quote }}
            - name: ZITADEL_FIRSTINSTANCE_ORG_MACHINE_MACHINE_USERNAME
              value: "bootstrap-automation"
            - name: ZITADEL_FIRSTINSTANCE_ORG_MACHINE_MACHINE_NAME
              value: "bootstrap-automation"
            - name: ZITADEL_FIRSTINSTANCE_ORG_MACHINE_PAT_EXPIRATIONDATE
              value: "2030-01-01T00:00:00Z"
            - name: ZITADEL_FIRSTINSTANCE_PATPATH
              value: "/pat/pat.txt"
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /debug/healthz
              port: 8080
            initialDelaySeconds: 15
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /debug/healthz
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 30
```

The zitadel-user Postgres secret uses the same SUPERUSER role for both `USER_*` and `ADMIN_*` env vars, matching Task 1's `options: "SUPERUSER"` choice (mirrors the existing `opentourney` app user's own permissive-for-staging convention rather than introducing a new least-privilege pattern this chart doesn't otherwise use).

- [ ] **Step 4: Write the Service template**

Create `charts/opentourney/templates/zitadel-service.yaml`:

```yaml
{{- if .Values.zitadel.enabled }}
apiVersion: v1
kind: Service
metadata:
  name: zitadel
  labels:
    {{- include "ot.labels" . | nindent 4 }}
spec:
  selector:
    app.kubernetes.io/component: zitadel
    app.kubernetes.io/instance: {{ .Release.Name }}
  ports:
    - port: 8080
      targetPort: 8080
{{- end }}
```

Named `zitadel` (not templated with `ot.fullname`) so the resulting DNS name is the short, predictable `zitadel.opentourney-staging.svc.cluster.local` referenced in `values.yaml`'s `externalDomain` — same reasoning as the existing `backend`/`frontend` Service names in this chart.

- [ ] **Step 5: Render and verify**

Run: `helm template charts/opentourney --set percona.enabled=true --set zitadel.enabled=true --set zitadel.masterkey=$(openssl rand -base64 24 | head -c 32) --set zitadel.firstInstance.adminPassword='Test1234!' --set secrets.databaseUrl=x --set secrets.oidcIssuer=x --set secrets.oidcAudience=x --set secrets.oidcJwksStatic=x`
Expected: renders cleanly, no template errors; `Deployment/opentourney-staging-opentourney-zitadel` and `Service/zitadel` both present in the output.

- [ ] **Step 6: Commit**

```bash
git add charts/opentourney/templates/zitadel-secret.yaml charts/opentourney/templates/zitadel-deployment.yaml charts/opentourney/templates/zitadel-service.yaml charts/opentourney/values.yaml
git commit -m "feat(helm): add Zitadel Deployment/Service, masterkey secret, FirstInstance bootstrap config"
```

- [ ] **Step 7: Deploy to staging and verify Zitadel comes up standalone**

```bash
helm --kube-context mcgee-local upgrade opentourney-staging charts/opentourney \
  --namespace opentourney-staging --reuse-values --force-conflicts \
  --set zitadel.enabled=true \
  --set-string zitadel.masterkey=$(openssl rand -base64 24 | head -c 32) \
  --set-string zitadel.firstInstance.adminPassword='<a-real-password-meeting-the-complexity-rule>'
kubectl --context mcgee-local -n opentourney-staging rollout status deployment/opentourney-staging-opentourney-zitadel --timeout=180s
kubectl --context mcgee-local -n opentourney-staging port-forward svc/zitadel 8080:8080
```

Run the `port-forward` in a separate terminal, then open `http://localhost:8080/ui/console` in a browser.

Expected: Zitadel's real login page loads, and the FirstInstance admin credentials from the `--set-string` flags above log in successfully.

---

### Task 3: Bootstrap sidecar — project, roles, test users, and the roles-claim Action

**Files:**
- Create: `charts/opentourney/files/bootstrap.py`
- Modify: `charts/opentourney/templates/zitadel-deployment.yaml` (add the sidecar container)
- Modify: `charts/opentourney/templates/zitadel-secret.yaml` (no changes needed — sidecar reads the PAT from the shared `emptyDir`, not a Secret)

**Interfaces:**
- Consumes: the PAT written to `/pat/pat.txt` by the `zitadel` container (Task 2); Zitadel's Management API at `http://localhost:8080/management/v1`.
- Produces: an OpenTourney project in Zitadel with 3 roles (`organizer`, `scorekeeper`, `player`), 3 human users (`organizer@staging.local`, `scorekeeper@staging.local`, `player@staging.local`) each granted their matching role, and a Complement Token Action asserting a flat `roles` claim — consumed by Phase 15's backend cutover (tokens must decode successfully) and Phase 16's frontend login (these are the 3 accounts testers log in with).

Before writing `bootstrap.py`, fetch and confirm the exact current request/response JSON shape for each of these Management API endpoints (proto field names are `snake_case`; the JSON gateway typically uses `camelCase` — confirm the actual casing against a live call, not assumed):
- `POST /management/v1/projects` (create project)
- `POST /management/v1/projects/{projectId}/roles` (add project role)
- `POST /management/v1/users/human/_import` or `POST /management/v1/users/human` (create human user — confirm which endpoint is current for this Zitadel version)
- `POST /management/v1/users/{userId}/grants` (grant a user their project role)
- `POST /management/v1/actions` (create the Action, JS source from below)
- `POST /management/v1/flows/{flowType}/trigger/{triggerType}` (attach the Action to the Complement Token flow's "Pre Userinfo creation" and "Pre access token creation" triggers)

Reference: `https://zitadel.com/docs/apis/resources/mgmt` (Management API v1) — fetch the live current page rather than relying on this plan's endpoint paths going stale.

- [ ] **Step 1: Write the Action's JavaScript source as a Python string constant**

The Complement Token Action body (verified against `https://zitadel.com/docs/apis/actions/code-examples`):

```javascript
function addRolesClaim(ctx, api) {
  let roles = [];
  ctx.v1.user.grants.grants.forEach(function (grant) {
    grant.roles.forEach(function (role) {
      roles.push(role);
    });
  });
  api.v1.claims.setClaim("roles", roles);
}
```

- [ ] **Step 2: Write `bootstrap.py`**

Create `charts/opentourney/files/bootstrap.py` — a single script, run once per Pod start, idempotent (treats a 409/"already exists" response from any create-call as success rather than failing):

```python
#!/usr/bin/env python3
import os
import sys
import time

import requests

ZITADEL_BASE = "http://localhost:8080"
PAT_PATH = "/pat/pat.txt"
ROLES = ["organizer", "scorekeeper", "player"]
PROJECT_NAME = "OpenTourney"

ACTION_SOURCE = """
function addRolesClaim(ctx, api) {
  let roles = [];
  ctx.v1.user.grants.grants.forEach(function (grant) {
    grant.roles.forEach(function (role) {
      roles.push(role);
    });
  });
  api.v1.claims.setClaim("roles", roles);
}
"""


def wait_for_pat(timeout_seconds=300):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if os.path.exists(PAT_PATH):
            with open(PAT_PATH) as f:
                pat = f.read().strip()
            if pat:
                return pat
        time.sleep(2)
    raise TimeoutError(f"{PAT_PATH} did not appear within {timeout_seconds}s")


def api_post(session, path, json_body):
    response = session.post(f"{ZITADEL_BASE}{path}", json=json_body)
    if response.status_code == 409:
        return None  # already exists — idempotent no-op
    response.raise_for_status()
    return response.json()


def main():
    pat = wait_for_pat()
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {pat}"

    # NOTE: exact request/response field names below must be confirmed
    # against a live fetch of https://zitadel.com/docs/apis/resources/mgmt
    # at implementation time — this is a starting shape, not a verified one.
    project = api_post(session, "/management/v1/projects", {"name": PROJECT_NAME})
    # ... resolve project_id whether just-created or pre-existing (GET by name
    # if api_post returned None), then create roles/users/grants/action/trigger
    # following the same create-or-409-noop pattern.

    print("bootstrap complete")


if __name__ == "__main__":
    main()
```

This is intentionally a skeleton for the parts whose exact API shape needs a live-docs check (project/role/user/grant/action creation, and resolving an already-existing project's ID on a re-run) — Step 1's JS source and the PAT-wait/session/idempotency scaffolding are concrete and final. The implementer completes the `main()` body using the confirmed field names from the live Management API docs fetch called for above, following the same `api_post`-with-409-noop pattern for every create call, and adds a corresponding `GET`-by-name lookup before each create so a re-run resolves existing IDs instead of erroring.

- [ ] **Step 3: Mount `bootstrap.py` into the chart and add the sidecar container**

Add to `charts/opentourney/templates/zitadel-deployment.yaml`'s `spec.template.spec`:

```yaml
      volumes:
        - name: pat
          emptyDir: {}
        - name: bootstrap-script
          configMap:
            name: {{ include "ot.fullname" . }}-zitadel-bootstrap
      containers:
        - name: zitadel
          # ... (unchanged from Task 2)
        - name: bootstrap
          image: python:3.12-alpine
          command: ["sh", "-c", "pip install --no-cache-dir requests && python /scripts/bootstrap.py"]
          volumeMounts:
            - name: pat
              mountPath: /pat
            - name: bootstrap-script
              mountPath: /scripts
```

Add a new template `charts/opentourney/templates/zitadel-bootstrap-configmap.yaml`:

```yaml
{{- if .Values.zitadel.enabled }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "ot.fullname" . }}-zitadel-bootstrap
  labels:
    {{- include "ot.labels" . | nindent 4 }}
data:
  bootstrap.py: |-
{{ .Files.Get "files/bootstrap.py" | indent 4 }}
{{- end }}
```

- [ ] **Step 4: Render and verify**

Run: `helm template charts/opentourney --set percona.enabled=true --set zitadel.enabled=true --set zitadel.masterkey=$(openssl rand -base64 24 | head -c 32) --set zitadel.firstInstance.adminPassword='Test1234!' --set secrets.databaseUrl=x --set secrets.oidcIssuer=x --set secrets.oidcAudience=x --set secrets.oidcJwksStatic=x`
Expected: `ConfigMap/opentourney-staging-opentourney-zitadel-bootstrap` renders with `bootstrap.py`'s contents inline; the Zitadel `Deployment` now has 2 containers (`zitadel`, `bootstrap`).

- [ ] **Step 5: Commit**

```bash
git add charts/opentourney/files/bootstrap.py charts/opentourney/templates/zitadel-deployment.yaml charts/opentourney/templates/zitadel-bootstrap-configmap.yaml
git commit -m "feat(helm): add Zitadel bootstrap sidecar (project/roles/test users/roles-claim action)"
```

- [ ] **Step 6: Deploy and verify end-to-end**

```bash
helm --kube-context mcgee-local upgrade opentourney-staging charts/opentourney \
  --namespace opentourney-staging --reuse-values --force-conflicts
kubectl --context mcgee-local -n opentourney-staging rollout status deployment/opentourney-staging-opentourney-zitadel --timeout=180s
kubectl --context mcgee-local -n opentourney-staging logs deployment/opentourney-staging-opentourney-zitadel -c bootstrap
```
Expected: bootstrap container's logs end with `bootstrap complete`, no unhandled exceptions.

```bash
kubectl --context mcgee-local -n opentourney-staging port-forward svc/zitadel 8080:8080
```
In a browser, log in as `organizer@staging.local` through Zitadel's real login page, then use Zitadel's own token endpoint/Console to inspect the issued token's claims (or `kubectl exec` into the bootstrap container and `curl` the token endpoint directly with the test user's credentials via the Resource Owner Password grant, enabled by default for testing).
Expected: the token's claims include a flat `"roles": ["organizer"]` array — the exact shape `identity_from_claims` (`backend/app/auth/identity.py:26`) parses.

Re-run the same `helm upgrade` a second time.
Expected: bootstrap container's logs again end with `bootstrap complete`, with no errors from re-attempting already-created resources (confirms idempotency).

---

## Self-Review Notes

- **Spec coverage**: covers the design spec's Phase A in full — chart toggle, Postgres reuse, bootstrap automation, roles-claim shaping, standalone verification via Zitadel's own login page. Phases B (backend cutover) and C (frontend integration) are separate plans, written when those phases are picked up, per the phase breakdown.
- **Known gap, intentional**: Task 3's `bootstrap.py` `main()` body is a scaffold, not a finished script — the exact Management API request/response field names could not be verified with full confidence in this planning pass (several fetches returned partial/inconsistent info, e.g. `FIRSTINSTANCE` vs `DEFAULTINSTANCE` naming). Rather than write plausible-but-unverified JSON bodies into the plan as fact, Task 3 Step 2 requires a live docs fetch at implementation time to complete it correctly. Everything else in this plan (image, env vars, PAT mechanism, Action JS source, chart structure) was cross-confirmed against current Zitadel documentation and/or existing chart patterns.
- **Type consistency**: `zitadel.masterkey`, `zitadel.firstInstance.adminPassword`, `zitadel.enabled` used consistently across Tasks 1-3; Service name `zitadel` (Task 2 Step 4) matches `values.yaml`'s `externalDomain` (Task 1 Step 2) and Task 3's `ZITADEL_BASE = "http://localhost:8080"` (same-Pod, so `localhost`, not the Service DNS name).
