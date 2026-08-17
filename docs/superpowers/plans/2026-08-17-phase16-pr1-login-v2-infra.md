# Phase 16 PR1 — Login V2 Infra + Bootstrap App Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy Zitadel's Login V2 UI as a new chart component so `/oauth/v2/authorize` has somewhere to redirect to, register a second OIDC app for the frontend, and complete the real end-to-end curl verification Phase 15 deferred.

**Architecture:** A new `<release>-zitadel-login` Deployment/Service runs the official `ghcr.io/zitadel/zitadel-login` container. It authenticates to core Zitadel via the official X.509-JWT `SystemAPIUsers` mechanism (a chart-generated RSA keypair — public cert trusted by core via a new mounted YAML config file, private key mounted into the login pod). `bootstrap.py` gains a second OIDC app registration (`opentourney-frontend`, `USER_AGENT` type, for PR2's frontend) and one Instance Feature API call to point core at the new login service. No backend application code changes.

**Tech Stack:** Helm (new/modified templates), Python (`bootstrap.py`, `requests` only), Zitadel Management API v1 + Feature API v2 (REST/JSON), `kubectl`, `curl`.

## Global Constraints

- Zero backend application code changes (`backend/app/**` untouched).
- `bootstrap.py` changes follow its existing idempotent get-or-create pattern (treat 409 as no-op, resolve existing resource via search) — every resource in the file already does this.
- Login V2 credential scheme: X.509 JWT via `SystemAPIUsers` (the official Zitadel pattern), not a PAT — confirmed by reading `zitadel-charts`' own `deployment_login.yaml`/`configmap_login.yaml`/`secret_login-service-key.yaml`/`values.yaml` directly, not third-party writeups.
- `opentourney-cli` (existing Native app from Phase 15) is untouched — this PR only adds a second app, `opentourney-frontend`.
- `SetInstanceFeatures`' `loginV2.baseUri` must be the **bare host** (e.g. `http://<release>-zitadel-login:3000`), not suffixed with `/ui/v2/login` — Zitadel's `defaultBaseURL()` appends that path itself; a pre-suffixed value produces a double path (confirmed via a `zitadel-charts` GitHub issue on this exact footgun).
- External (Cloudflare tunnel) routing for core Zitadel / Login V2 is out of scope for this PR — verification below uses `kubectl port-forward`, same as Phase 15.

---

### Task 1: Add `zitadel.login` values

**Files:**
- Modify: `charts/opentourney/values.yaml:44-62` (existing `zitadel:` block)
- Modify: `charts/opentourney/values.staging.yaml:31-32` (existing `zitadel:` block)

**Interfaces:**
- Consumes: nothing new.
- Produces: `.Values.zitadel.login.enabled`, `.Values.zitadel.login.image.repository`, `.Values.zitadel.login.image.tag`, `.Values.zitadel.login.image.pullPolicy` — every later task's templates read these.

- [ ] **Step 1: Add the `login` sub-block to `values.yaml`**

Find (`charts/opentourney/values.yaml:44-62`):

```yaml
zitadel:
  enabled: false
  image:
    repository: ghcr.io/zitadel/zitadel
    tag: v4.17.1
    pullPolicy: IfNotPresent
```

Replace with:

```yaml
zitadel:
  enabled: false
  image:
    repository: ghcr.io/zitadel/zitadel
    tag: v4.17.1
    pullPolicy: IfNotPresent
  # Zitadel v4's core binary no longer serves login pages itself -- every
  # /oauth/v2/authorize redirects to this separate service. Defaults to
  # enabled whenever zitadel.enabled is true: there is no supported way to
  # complete a real login (browser or curl) without it.
  login:
    enabled: true
    image:
      repository: ghcr.io/zitadel/zitadel-login
      # Pinned to the same release as zitadel.image.tag above -- Zitadel
      # versions core and Login V2 together. Confirm this tag exists at
      # deploy time (Task 8); bump both tags together on future upgrades.
      tag: v4.17.1
      pullPolicy: IfNotPresent
```

(Leave the rest of the existing `zitadel:` block — `externalDomain`, `externalPort`, `masterkey`, `firstInstance` — unchanged.)

- [ ] **Step 2: Confirm `values.staging.yaml` needs no change**

`charts/opentourney/values.staging.yaml:31-32` only sets `zitadel.enabled: true` and `zitadel.externalDomain`; `zitadel.login.enabled` defaults to `true` from `values.yaml` and staging doesn't override the image, so no edit is needed here. (No-op step — confirms the inheritance instead of guessing.)

- [ ] **Step 3: Commit**

```bash
git add charts/opentourney/values.yaml
git commit -m "feat(zitadel): add login.* values for Login V2 deployment

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Login V2 service-key Secret (RSA keypair)

**Files:**
- Create: `charts/opentourney/templates/zitadel-login-secret.yaml`

**Interfaces:**
- Consumes: `.Values.zitadel.enabled`, `.Values.zitadel.login.enabled` (Task 1), `ot.fullname`/`ot.labels` helpers (existing, used by every other template in this chart).
- Produces: Secret `<release>-zitadel-login-service-key` with keys `tls.crt` (public cert, consumed by Task 3's core-trust config) and `tls.key` (private key, consumed by Task 4's login Deployment).

- [ ] **Step 1: Write the Secret template**

Create `charts/opentourney/templates/zitadel-login-secret.yaml`:

```yaml
{{- if and .Values.zitadel.enabled .Values.zitadel.login.enabled }}
{{- $secretName := printf "%s-zitadel-login-service-key" (include "ot.fullname" .) }}
{{- $existing := lookup "v1" "Secret" .Release.Namespace $secretName }}
{{- if and $existing $existing.data (hasKey $existing.data "tls.crt") (hasKey $existing.data "tls.key") }}
# Reuse the existing keypair on upgrade -- a new cert on every `helm upgrade`
# would break core Zitadel's SystemAPIUsers trust of the login client's JWTs
# (Task 3) until both sides picked up the new cert simultaneously.
apiVersion: v1
kind: Secret
metadata:
  name: {{ $secretName }}
  labels:
    {{- include "ot.labels" . | nindent 4 }}
type: kubernetes.io/tls
data:
  tls.crt: {{ index $existing.data "tls.crt" }}
  tls.key: {{ index $existing.data "tls.key" }}
{{- else }}
{{- $cert := genSelfSignedCert "login-service" nil (list "login-service") 3650 }}
apiVersion: v1
kind: Secret
metadata:
  name: {{ $secretName }}
  labels:
    {{- include "ot.labels" . | nindent 4 }}
type: kubernetes.io/tls
data:
  tls.crt: {{ $cert.Cert | b64enc }}
  tls.key: {{ $cert.Key | b64enc }}
{{- end }}
{{- end }}
```

- [ ] **Step 2: Helm lint + template render**

Run:

```bash
helm lint charts/opentourney
helm template opentourney-staging charts/opentourney \
  -f charts/opentourney/values.staging.yaml \
  --set-string secrets.databaseUrl=postgres://x \
  --set-string secrets.oidcIssuer=http://x \
  --set-string secrets.oidcAudience=x \
  --set-string secrets.oidcJwksStatic='{"keys":[]}' \
  --set-string zitadel.masterkey=12345678901234567890123456789012 \
  --set-string zitadel.firstInstance.adminPassword='Abcdef1!' \
  | python3 -c "import sys, yaml; list(yaml.safe_load_all(sys.stdin))" \
  && echo RENDER_OK
```

Expected: `helm lint` reports 0 charts failed, `RENDER_OK` prints. Grep the raw `helm template` output for `zitadel-login-service-key` and confirm a single `Secret` with `type: kubernetes.io/tls` renders.

- [ ] **Step 3: Commit**

```bash
git add charts/opentourney/templates/zitadel-login-secret.yaml
git commit -m "feat(zitadel): generate Login V2 service-key RSA keypair

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Core Zitadel trusts the login client (`SystemAPIUsers`)

**Files:**
- Create: `charts/opentourney/templates/zitadel-system-api-users-configmap.yaml`
- Modify: `charts/opentourney/templates/zitadel-deployment.yaml:41-54` (volumes)
- Modify: `charts/opentourney/templates/zitadel-deployment.yaml:51-54` (args + volumeMounts)

**Interfaces:**
- Consumes: Task 2's Secret (`<release>-zitadel-login-service-key`, `tls.crt` key).
- Produces: core Zitadel accepts JWTs signed by the login service's private key as the `login-client` system API user with `IAM_LOGIN_CLIENT` — Task 6's `enable_login_v2_feature()` and Task 4's login pod both depend on this being live before they're useful.

- [ ] **Step 1: Write the `SystemAPIUsers` config ConfigMap**

`SystemAPIUsers` is a dynamically-keyed map in Zitadel's config schema, which this chart's env-var-driven core config can't express (env vars need a static key per value; Zitadel doesn't expose a `ZITADEL_SYSTEMAPIUSERS_LOGIN_CLIENT_...` style override for map entries). Zitadel's CLI supports layering a `--config <path>` YAML file on top of env vars for exactly this kind of dynamic-map config — grounded in `zitadel-charts`' own `values.yaml`, which documents `SystemAPIUsers.<name>.Path`/`Memberships[].MemberType`/`Memberships[].Roles` as the field names (PascalCase, matching Zitadel's Go config struct).

Create `charts/opentourney/templates/zitadel-system-api-users-configmap.yaml`:

```yaml
{{- if and .Values.zitadel.enabled .Values.zitadel.login.enabled }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "ot.fullname" . }}-zitadel-system-api-users
  labels:
    {{- include "ot.labels" . | nindent 4 }}
data:
  system-api-users.yaml: |
    SystemAPIUsers:
      login-client:
        Path: /login-client-cert/tls.crt
        Memberships:
          - MemberType: System
            Roles:
              - IAM_LOGIN_CLIENT
{{- end }}
```

- [ ] **Step 2: Mount the cert and config file into core's container, add `--config`**

In `charts/opentourney/templates/zitadel-deployment.yaml`, find:

```yaml
      volumes:
        - name: pat
          emptyDir: {}
        - name: bootstrap-script
          configMap:
            name: {{ include "ot.fullname" . }}-zitadel-bootstrap
      containers:
        - name: zitadel
          image: "{{ .Values.zitadel.image.repository }}:{{ .Values.zitadel.image.tag }}"
          imagePullPolicy: {{ .Values.zitadel.image.pullPolicy }}
          args: ["start-from-init", "--masterkeyFromEnv"]
          volumeMounts:
            - name: pat
              mountPath: /pat
```

Replace with:

```yaml
      volumes:
        - name: pat
          emptyDir: {}
        - name: bootstrap-script
          configMap:
            name: {{ include "ot.fullname" . }}-zitadel-bootstrap
        {{- if .Values.zitadel.login.enabled }}
        - name: login-client-cert
          secret:
            secretName: {{ printf "%s-zitadel-login-service-key" (include "ot.fullname" .) }}
            items:
              - key: tls.crt
                path: tls.crt
        - name: system-api-users-config
          configMap:
            name: {{ include "ot.fullname" . }}-zitadel-system-api-users
        {{- end }}
      containers:
        - name: zitadel
          image: "{{ .Values.zitadel.image.repository }}:{{ .Values.zitadel.image.tag }}"
          imagePullPolicy: {{ .Values.zitadel.image.pullPolicy }}
          args:
            - start-from-init
            - --masterkeyFromEnv
            {{- if .Values.zitadel.login.enabled }}
            - --config
            - /config/system-api-users.yaml
            {{- end }}
          volumeMounts:
            - name: pat
              mountPath: /pat
            {{- if .Values.zitadel.login.enabled }}
            - name: login-client-cert
              mountPath: /login-client-cert
              readOnly: true
            - name: system-api-users-config
              mountPath: /config
              readOnly: true
            {{- end }}
```

- [ ] **Step 3: Bump the restart-checksum annotation to cover the new config**

The pod template already restarts on `bootstrap.py` changes via a checksum annotation. Find (`zitadel-deployment.yaml:23-28`):

```yaml
      annotations:
        # Ties the pod template to the bootstrap script's content so a bootstrap.py edit
        # + `helm upgrade` actually restarts the pod and picks up the fix. Safe now that the
        # PAT is persisted to a Secret (see the "bootstrap" container below) rather than only
        # living in the emptyDir — a pod replacement no longer loses the one-shot credential.
        checksum/bootstrap-configmap: {{ include (print $.Template.BasePath "/zitadel-bootstrap-configmap.yaml") . | sha256sum }}
```

Replace with:

```yaml
      annotations:
        # Ties the pod template to the bootstrap script's content so a bootstrap.py edit
        # + `helm upgrade` actually restarts the pod and picks up the fix. Safe now that the
        # PAT is persisted to a Secret (see the "bootstrap" container below) rather than only
        # living in the emptyDir — a pod replacement no longer loses the one-shot credential.
        checksum/bootstrap-configmap: {{ include (print $.Template.BasePath "/zitadel-bootstrap-configmap.yaml") . | sha256sum }}
        {{- if .Values.zitadel.login.enabled }}
        # Same reasoning, for the SystemAPIUsers config -- core only re-reads --config
        # files on process start, so a content change needs a pod restart to take effect.
        checksum/system-api-users-configmap: {{ include (print $.Template.BasePath "/zitadel-system-api-users-configmap.yaml") . | sha256sum }}
        {{- end }}
```

- [ ] **Step 4: Helm lint + template render**

Run the same render command as Task 2 Step 2. Expected: `RENDER_OK`; grep the output for `--config` and `/config/system-api-users.yaml` under the `zitadel` container's `args`, and confirm `login-client-cert`/`system-api-users-config` volumes appear.

- [ ] **Step 5: Commit**

```bash
git add charts/opentourney/templates/zitadel-system-api-users-configmap.yaml \
        charts/opentourney/templates/zitadel-deployment.yaml
git commit -m "feat(zitadel): trust the Login V2 client via SystemAPIUsers

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: Login V2 Deployment + Service + `.env` config

**Files:**
- Create: `charts/opentourney/templates/zitadel-login-configmap.yaml`
- Create: `charts/opentourney/templates/zitadel-login-deployment.yaml`
- Create: `charts/opentourney/templates/zitadel-login-service.yaml`

**Interfaces:**
- Consumes: Task 1's `.Values.zitadel.login.*`, Task 2's Secret (`tls.key` key), `.Values.zitadel.externalDomain`/`externalPort` (existing).
- Produces: Service `<release>-zitadel-login` on port 3000, reachable in-cluster at `http://<release>-zitadel-login:3000` — Task 6's `baseUri` and DEVELOPMENT.md's verification recipe (Task 7) both depend on this exact address.

- [ ] **Step 1: Write the `.env` ConfigMap**

Create `charts/opentourney/templates/zitadel-login-configmap.yaml`:

```yaml
{{- if and .Values.zitadel.enabled .Values.zitadel.login.enabled }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "ot.fullname" . }}-zitadel-login-config
  labels:
    {{- include "ot.labels" . | nindent 4 }}
data:
  # Consumed by the login container's own entrypoint, which shell-expands
  # ${ZITADEL_EXTERNALDOMAIN} (set as a plain container env var below) into
  # AUDIENCE/CUSTOM_REQUEST_HEADERS at startup -- mirrors zitadel-charts'
  # configmap_login.yaml exactly (this content isn't something we invented;
  # it's the shape the official image's entrypoint expects).
  .env: |-
    ZITADEL_LOGINCLIENT_KEYFILE="/login-service-key/tls.key"
    AUDIENCE="http://${ZITADEL_EXTERNALDOMAIN}"
    # NOT ot.fullname-prefixed: charts/opentourney/templates/zitadel-service.yaml
    # names core Zitadel's Service the bare literal "zitadel" (a pre-existing
    # Phase 14 exception to this chart's usual naming, unrelated to Login V2).
    ZITADEL_API_URL="http://zitadel:8080"
    CUSTOM_REQUEST_HEADERS="Host:${ZITADEL_EXTERNALDOMAIN},X-Zitadel-Public-Host:${ZITADEL_EXTERNALDOMAIN}"
{{- end }}
```

- [ ] **Step 2: Write the Deployment**

Create `charts/opentourney/templates/zitadel-login-deployment.yaml`:

```yaml
{{- if and .Values.zitadel.enabled .Values.zitadel.login.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "ot.fullname" . }}-zitadel-login
  labels:
    {{- include "ot.labels" . | nindent 4 }}
    app.kubernetes.io/component: zitadel-login
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/component: zitadel-login
      app.kubernetes.io/instance: {{ .Release.Name }}
  template:
    metadata:
      labels:
        app.kubernetes.io/component: zitadel-login
        app.kubernetes.io/instance: {{ .Release.Name }}
      annotations:
        checksum/login-configmap: {{ include (print $.Template.BasePath "/zitadel-login-configmap.yaml") . | sha256sum }}
    spec:
      {{- with .Values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      initContainers:
        # Same dependency-ordering problem the "bootstrap" sidecar solves for
        # itself in zitadel-deployment.yaml, applied here: the login container
        # errors out (rather than retrying) if core Zitadel isn't answering yet.
        - name: wait-for-zitadel
          image: curlimages/curl:8.10.1
          command:
            - sh
            - -c
            - |
              until curl -sf http://zitadel:8080/debug/healthz; do
                echo "waiting for zitadel core..."
                sleep 5
              done
      containers:
        - name: login
          image: "{{ .Values.zitadel.login.image.repository }}:{{ .Values.zitadel.login.image.tag }}"
          imagePullPolicy: {{ .Values.zitadel.login.image.pullPolicy }}
          env:
            - name: NEXT_PUBLIC_BASE_PATH
              value: /ui/v2/login
            - name: ZITADEL_EXTERNALDOMAIN
              value: {{ .Values.zitadel.externalDomain | default (printf "zitadel.%s.svc.cluster.local" .Release.Namespace) | quote }}
          ports:
            - containerPort: 3000
          volumeMounts:
            - name: login-config-dotenv
              mountPath: /.env-file/
              readOnly: true
            - name: login-service-key
              mountPath: /login-service-key
              readOnly: true
          readinessProbe:
            httpGet:
              path: /ui/v2/login/ready
              port: 3000
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /ui/v2/login/healthy
              port: 3000
            initialDelaySeconds: 15
            periodSeconds: 30
            failureThreshold: 6
      volumes:
        - name: login-config-dotenv
          configMap:
            name: {{ include "ot.fullname" . }}-zitadel-login-config
        - name: login-service-key
          secret:
            secretName: {{ printf "%s-zitadel-login-service-key" (include "ot.fullname" .) }}
            items:
              - key: tls.key
                path: tls.key
{{- end }}
```

- [ ] **Step 3: Write the Service**

Create `charts/opentourney/templates/zitadel-login-service.yaml`:

```yaml
{{- if and .Values.zitadel.enabled .Values.zitadel.login.enabled }}
apiVersion: v1
kind: Service
metadata:
  name: {{ include "ot.fullname" . }}-zitadel-login
  labels:
    {{- include "ot.labels" . | nindent 4 }}
spec:
  selector:
    app.kubernetes.io/component: zitadel-login
    app.kubernetes.io/instance: {{ .Release.Name }}
  ports:
    - port: 3000
      targetPort: 3000
{{- end }}
```

- [ ] **Step 4: Helm lint + template render**

Run the same render command as Task 2 Step 2. Expected: `RENDER_OK`; grep the output for `kind: Deployment` with `name: opentourney-staging-opentourney-zitadel-login` and `kind: Service` with the same name suffix.

- [ ] **Step 5: Commit**

```bash
git add charts/opentourney/templates/zitadel-login-configmap.yaml \
        charts/opentourney/templates/zitadel-login-deployment.yaml \
        charts/opentourney/templates/zitadel-login-service.yaml
git commit -m "feat(zitadel): deploy Login V2 UI as a chart component

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: Parameterize `get_or_create_application()`, register `opentourney-frontend`

**Files:**
- Modify: `charts/opentourney/files/bootstrap.py:52-56` (constants)
- Modify: `charts/opentourney/files/bootstrap.py:202-235` (function signature/body)
- Modify: `charts/opentourney/files/bootstrap.py:420-426` (call sites in `main()`)

**Interfaces:**
- Consumes: `api_post(session, path, json_body)` (existing, `bootstrap.py:153`), `MGMT` constant (existing, `bootstrap.py:42`).
- Produces: `get_or_create_application(session, project_id, name, app_type, redirect_uris) -> str`. PR2 (frontend) relies on the `opentourney-frontend` client_id being logged as `application 'opentourney-frontend' client_id=...`, same convention as the existing `opentourney-cli` line.

- [ ] **Step 1: Add frontend app constants**

Find (`bootstrap.py:52-56`):

```python
APP_NAME = "opentourney-cli"
# Nothing listens on this port. The Authorization Code lands in the browser's
# address bar as a 404 on redirect; it's copied out manually for the curl token
# exchange (see DEVELOPMENT.md's "Verifying a real Zitadel login" section).
APP_REDIRECT_URI = "http://localhost:8765/callback"
```

Replace with:

```python
CLI_APP_NAME = "opentourney-cli"
# Nothing listens on this port. The Authorization Code lands in the browser's
# address bar as a 404 on redirect; it's copied out manually for the curl token
# exchange (see DEVELOPMENT.md's "Verifying a real Zitadel login" section).
CLI_APP_REDIRECT_URI = "http://localhost:8765/callback"
FRONTEND_APP_NAME = "opentourney-frontend"
# The frontend's actual origin varies per environment (staging vs. a future
# prod). Kept as a single staging-hardcoded value for now, matching this
# chart's existing scope (opentourney-staging only) -- revisit if/when a
# second environment needs its own app registration.
FRONTEND_APP_REDIRECT_URI = "http://opentourney-staging.local/callback"
```

- [ ] **Step 2: Parameterize `get_or_create_application()`**

Find (`bootstrap.py:202-235`):

```python
def get_or_create_application(session, project_id):
    body = {
        "name": APP_NAME,
        "redirectUris": [APP_REDIRECT_URI],
        "responseTypes": ["OIDC_RESPONSE_TYPE_CODE"],
        "grantTypes": ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"],
        # Public client (no secret) using PKCE, appropriate for this phase's manual
        # curl-based Authorization Code flow. Note: OIDC_APP_TYPE_NATIVE is for
        # loopback/custom-scheme redirect URIs (RFC 8252), not what Zitadel
        # recommends for a browser SPA (OIDC_APP_TYPE_USER_AGENT) -- Phase 16's
        # frontend oidc-client-ts integration will likely need a different app.
        "appType": "OIDC_APP_TYPE_NATIVE",
        "authMethodType": "OIDC_AUTH_METHOD_TYPE_NONE",
        "version": "OIDC_VERSION_1_0",
        # Mandatory: Zitadel's default access token is opaque. The backend's
        # RS256/JWKS verification (RemoteJWKSProvider) can only validate a JWT.
        "accessTokenType": "OIDC_TOKEN_TYPE_JWT",
    }
    result = api_post(session, f"/projects/{project_id}/apps/oidc", body)
    if result is not None:
        return result["clientId"]

    response = session.post(f"{MGMT}/projects/{project_id}/apps/_search", json={})
    response.raise_for_status()
    for app in response.json().get("result", []):
        if app.get("name") == APP_NAME:
            app_id = app["id"]
            break
    else:
        raise RuntimeError(f"application {APP_NAME!r} 409'd on create but not found in search")

    detail = session.get(f"{MGMT}/projects/{project_id}/apps/{app_id}")
    detail.raise_for_status()
    return detail.json()["app"]["oidcConfig"]["clientId"]
```

Replace with:

```python
def get_or_create_application(session, project_id, name, app_type, redirect_uris):
    body = {
        "name": name,
        "redirectUris": redirect_uris,
        "responseTypes": ["OIDC_RESPONSE_TYPE_CODE"],
        "grantTypes": ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"],
        # Public client (no secret) using PKCE for both app types this function
        # registers: OIDC_APP_TYPE_NATIVE is for loopback/custom-scheme redirect
        # URIs (RFC 8252, opentourney-cli's curl-testing use case);
        # OIDC_APP_TYPE_USER_AGENT is Zitadel's recommended type for a browser
        # SPA (opentourney-frontend, PR2's oidc-client-ts integration) -- the two
        # apps exist precisely so each client uses the type Zitadel recommends
        # for its actual use case instead of sharing one mismatched app.
        "appType": app_type,
        "authMethodType": "OIDC_AUTH_METHOD_TYPE_NONE",
        "version": "OIDC_VERSION_1_0",
        # Mandatory: Zitadel's default access token is opaque. The backend's
        # RS256/JWKS verification (RemoteJWKSProvider) can only validate a JWT.
        "accessTokenType": "OIDC_TOKEN_TYPE_JWT",
    }
    result = api_post(session, f"/projects/{project_id}/apps/oidc", body)
    if result is not None:
        return result["clientId"]

    response = session.post(f"{MGMT}/projects/{project_id}/apps/_search", json={})
    response.raise_for_status()
    for app in response.json().get("result", []):
        if app.get("name") == name:
            app_id = app["id"]
            break
    else:
        raise RuntimeError(f"application {name!r} 409'd on create but not found in search")

    detail = session.get(f"{MGMT}/projects/{project_id}/apps/{app_id}")
    detail.raise_for_status()
    return detail.json()["app"]["oidcConfig"]["clientId"]
```

- [ ] **Step 3: Wire both calls into `main()`**

Find (`bootstrap.py:415-426`):

```python
    # Ordered after user/grant/action provisioning deliberately: if this call fails
    # (e.g. Zitadel rejects the redirect URI -- see DEVELOPMENT.md's devMode note),
    # the more essential provisioning above has already completed and survives a pod
    # restart via the idempotent get-or-create pattern, instead of a failure here
    # blocking test users/roles/the roles-claim Action every single retry.
    client_id = get_or_create_application(session, project_id)
    # Logged unconditionally (unlike test-user passwords, which are unrecoverable
    # after creation) since client_id is retrievable via the Management API on any
    # later run -- this line is a convenience for copy/paste into the next
    # `helm upgrade --set-string secrets.oidcAudience=<client_id>`, not the only
    # source of truth.
    print(f"application {APP_NAME!r} client_id={client_id}")
```

Replace with:

```python
    # Ordered after user/grant/action provisioning deliberately: if either call fails
    # (e.g. Zitadel rejects a redirect URI -- see DEVELOPMENT.md's devMode note), the
    # more essential provisioning above has already completed and survives a pod
    # restart via the idempotent get-or-create pattern, instead of a failure here
    # blocking test users/roles/the roles-claim Action every single retry.
    cli_client_id = get_or_create_application(
        session, project_id, CLI_APP_NAME, "OIDC_APP_TYPE_NATIVE", [CLI_APP_REDIRECT_URI]
    )
    # Logged unconditionally (unlike test-user passwords, which are unrecoverable
    # after creation) since client_id is retrievable via the Management API on any
    # later run -- this line is a convenience for copy/paste into the next
    # `helm upgrade --set-string secrets.oidcAudience=<client_id>`, not the only
    # source of truth.
    print(f"application {CLI_APP_NAME!r} client_id={cli_client_id}")

    frontend_client_id = get_or_create_application(
        session, project_id, FRONTEND_APP_NAME, "OIDC_APP_TYPE_USER_AGENT", [FRONTEND_APP_REDIRECT_URI]
    )
    print(f"application {FRONTEND_APP_NAME!r} client_id={frontend_client_id}")
```

- [ ] **Step 4: Local syntax check**

Run: `python3 -m py_compile charts/opentourney/files/bootstrap.py`
Expected: exits 0, no output.

- [ ] **Step 5: Helm render sanity check**

Run the same render command as Task 2 Step 2. Expected: `RENDER_OK` (proves the edited `bootstrap.py` still embeds as valid YAML inside its ConfigMap).

- [ ] **Step 6: Commit**

```bash
git add charts/opentourney/files/bootstrap.py
git commit -m "feat(zitadel): register a second OIDC app for the frontend SPA

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: Enable the Login V2 instance feature

**Files:**
- Modify: `charts/opentourney/files/bootstrap.py:41-42` (constant)
- Modify: `charts/opentourney/files/bootstrap.py` (new function, placed after `get_or_create_application()`)
- Modify: `charts/opentourney/files/bootstrap.py:426-`  (wire into `main()`, after both app registrations)

**Interfaces:**
- Consumes: `ZITADEL_BASE` constant (existing, `bootstrap.py:41`), `session` (authenticated `requests.Session`, existing pattern from `main()`).
- Produces: core Zitadel's `/oauth/v2/authorize` redirects into Task 4's login Service instead of 404ing — Task 8's live verification depends on this.

- [ ] **Step 1: Add the login-service base URI constant**

Find (`bootstrap.py:41-42`):

```python
ZITADEL_BASE = "http://localhost:8080"
MGMT = f"{ZITADEL_BASE}/management/v1"
```

Replace with:

```python
ZITADEL_BASE = "http://localhost:8080"
MGMT = f"{ZITADEL_BASE}/management/v1"
# In-cluster Service DNS name for the Login V2 deployment (see
# charts/opentourney/templates/zitadel-login-service.yaml). Bare host only --
# Zitadel's defaultBaseURL() appends /ui/v2/login itself; a pre-suffixed value
# here produces a double path. Unset (None) when zitadel.login.enabled=false --
# enable_login_v2_feature() must not run in that case (see main()).
LOGIN_V2_BASE_URI = os.environ.get("ZITADEL_LOGIN_V2_BASE_URI")
```

- [ ] **Step 2: Add `enable_login_v2_feature()`**

Add this function after `get_or_create_application()` (i.e. right before `def find_user_by_username(session, username):`):

```python
def enable_login_v2_feature(session):
    # Instance Feature API lives under /v2, not /management/v1 (MGMT) -- a
    # different base path than every other call in this script.
    response = session.put(
        f"{ZITADEL_BASE}/v2/features/instance",
        json={"loginV2": {"required": True, "baseUri": LOGIN_V2_BASE_URI}},
    )
    if not response.ok:
        print(
            f"PUT /v2/features/instance -> {response.status_code}: {response.text}",
            file=sys.stderr,
        )
    response.raise_for_status()
```

Naturally idempotent (no create/409 semantics here — `SetInstanceFeatures` always overwrites the named fields), so no get-or-create wrapper is needed, unlike every other resource in this file.

- [ ] **Step 3: Wire it into `main()`**

Find (end of `main()`, after both `get_or_create_application()` calls from Task 5):

```python
    frontend_client_id = get_or_create_application(
        session, project_id, FRONTEND_APP_NAME, "OIDC_APP_TYPE_USER_AGENT", [FRONTEND_APP_REDIRECT_URI]
    )
    print(f"application {FRONTEND_APP_NAME!r} client_id={frontend_client_id}")
```

Replace with:

```python
    frontend_client_id = get_or_create_application(
        session, project_id, FRONTEND_APP_NAME, "OIDC_APP_TYPE_USER_AGENT", [FRONTEND_APP_REDIRECT_URI]
    )
    print(f"application {FRONTEND_APP_NAME!r} client_id={frontend_client_id}")

    if LOGIN_V2_BASE_URI:
        enable_login_v2_feature(session)
        print(f"Login V2 feature enabled, baseUri={LOGIN_V2_BASE_URI}")
    else:
        print("ZITADEL_LOGIN_V2_BASE_URI unset (zitadel.login.enabled=false) -- skipping Login V2 feature enable")
```

- [ ] **Step 4: Set `ZITADEL_LOGIN_V2_BASE_URI` on the bootstrap sidecar container**

In `charts/opentourney/templates/zitadel-deployment.yaml`, find the `bootstrap` container's `env` block:

```yaml
        - name: bootstrap
          image: python:3.12-alpine
          command: ["sh", "-c", "pip install --no-cache-dir requests==2.32.3 && python /scripts/bootstrap.py; sleep infinity"]
          env:
            - name: ZITADEL_EXTERNAL_DOMAIN
              value: {{ .Values.zitadel.externalDomain | default (printf "zitadel.%s.svc.cluster.local" .Release.Namespace) | quote }}
            - name: ZITADEL_PAT_SECRET_NAME
              value: {{ printf "%s-zitadel-pat" (include "ot.fullname" .) | quote }}
```

Replace with:

```yaml
        - name: bootstrap
          image: python:3.12-alpine
          command: ["sh", "-c", "pip install --no-cache-dir requests==2.32.3 && python /scripts/bootstrap.py; sleep infinity"]
          env:
            - name: ZITADEL_EXTERNAL_DOMAIN
              value: {{ .Values.zitadel.externalDomain | default (printf "zitadel.%s.svc.cluster.local" .Release.Namespace) | quote }}
            - name: ZITADEL_PAT_SECRET_NAME
              value: {{ printf "%s-zitadel-pat" (include "ot.fullname" .) | quote }}
            {{- if .Values.zitadel.login.enabled }}
            - name: ZITADEL_LOGIN_V2_BASE_URI
              value: {{ printf "http://%s-zitadel-login:3000" (include "ot.fullname" .) | quote }}
            {{- end }}
```

- [ ] **Step 5: Local syntax check**

Run: `python3 -m py_compile charts/opentourney/files/bootstrap.py`
Expected: exits 0, no output.

- [ ] **Step 6: Helm render sanity check**

Run the same render command as Task 2 Step 2. Expected: `RENDER_OK`; grep the output for `ZITADEL_LOGIN_V2_BASE_URI` under the `bootstrap` container's `env`.

- [ ] **Step 7: Commit**

```bash
git add charts/opentourney/files/bootstrap.py charts/opentourney/templates/zitadel-deployment.yaml
git commit -m "feat(zitadel): enable Login V2 instance feature from bootstrap sidecar

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: Update deploy/verification docs

**Files:**
- Modify: `DEVELOPMENT.md` ("Verifying a real Zitadel login" section, `DEVELOPMENT.md:202-281`)

**Interfaces:**
- Consumes: Task 5's two logged `client_id` lines, Task 6's `LOGIN_V2_BASE_URI`.
- Produces: the exact recipe Task 8 (this PR) and PR2's frontend manual walkthrough both follow.

- [ ] **Step 1: Remove the "Known gap" callout and update the recipe to route through Login V2**

Find (`DEVELOPMENT.md:202-260`, the whole section through step 3):

```
### Verifying a real Zitadel login

Confirms the backend actually accepts a Zitadel-issued token end to end
(role claim, `source_system` claim, signature/issuer/audience validation) —
not just that the Helm secret values look right.

**Known gap:** Zitadel v4's Login V2 UI is a separate, standalone container
that this chart does not yet deploy — the core `zitadel` binary no longer
serves login pages itself. As a result, step 3 below (opening the authorize
URL in a browser and logging in) currently cannot complete; it 404s with
`{"code":5,"message":"Not Found"}` instead of redirecting to a login page.
Tracked in [issue #82](https://github.com/badconfigstudios/opentourney/issues/82)
(Phase 16 scope). Steps 1-2 and 5-7 remain the correct recipe once Login V2
is deployed — only step 3 is currently blocked.

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
   http://<zitadel-issuer-hostname>:8080/oauth/v2/authorize?client_id=<client-id-from-bootstrap-log>&redirect_uri=http://localhost:8765/callback&response_type=code&scope=openid+profile&code_challenge=<challenge>&code_challenge_method=S256
   ```

   Log in as `organizer@staging.local` with the password the bootstrap
   sidecar logged at creation time.
```

Replace with:

```
### Verifying a real Zitadel login

Confirms the backend actually accepts a Zitadel-issued token end to end
(role claim, `source_system` claim, signature/issuer/audience validation) —
not just that the Helm secret values look right.

Since Phase 16 PR1, Login V2 is deployed as its own chart component
(`charts/opentourney/templates/zitadel-login-*.yaml`) and core Zitadel is
configured to redirect `/oauth/v2/authorize` into it — step 3 below now
completes.

1. Port-forward Zitadel core and the Login V2 UI (two separate services):

   ```bash
   kubectl --context mcgee-local -n opentourney-staging port-forward svc/zitadel 8080:8080
   kubectl --context mcgee-local -n opentourney-staging port-forward svc/opentourney-staging-opentourney-zitadel-login 3000:3000
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
   http://<zitadel-issuer-hostname>:8080/oauth/v2/authorize?client_id=<opentourney-cli-client-id-from-bootstrap-log>&redirect_uri=http://localhost:8765/callback&response_type=code&scope=openid+profile&code_challenge=<challenge>&code_challenge_method=S256
   ```

   The browser should now redirect into `http://localhost:3000/ui/v2/login/...`
   (via the port-forward from step 1) instead of 404ing. Log in as
   `organizer@staging.local` with the password the bootstrap sidecar logged
   at creation time.
```

- [ ] **Step 2: Add a troubleshooting note for the `baseUri` double-path footgun**

Find the existing troubleshooting note at the end of the section (`DEVELOPMENT.md:348-354`):

```
**Troubleshooting the authorize call:** if Zitadel rejects the redirect URI
outright (400 on step 3, before any login page renders), the client likely
needs `"devMode": true` added to Task 1's `get_or_create_application()`
request body — Zitadel's default posture requires HTTPS redirect URIs for
non-loopback apps, and this deployment (`ZITADEL_EXTERNALSECURE=false`)
runs entirely over HTTP. Add the field, re-run the bootstrap Job/pod
restart, and retry.
```

Replace with:

```
**Troubleshooting the authorize call:** if Zitadel rejects the redirect URI
outright (400 on step 3, before any login page renders), the client likely
needs `"devMode": true` added to `get_or_create_application()`'s request
body — Zitadel's default posture requires HTTPS redirect URIs for
non-loopback apps, and this deployment (`ZITADEL_EXTERNALSECURE=false`)
runs entirely over HTTP. Add the field, re-run the bootstrap Job/pod
restart, and retry.

**Troubleshooting a double `/ui/v2/login/ui/v2/login` redirect:** the
bootstrap sidecar's `enable_login_v2_feature()` sets `loginV2.baseUri` to
the bare login-service host (`http://<release>-zitadel-login:3000`) —
Zitadel's `defaultBaseURL()` appends `/ui/v2/login` itself. If the browser
lands on a doubled path, check
`kubectl -n opentourney-staging exec deploy/opentourney-staging-opentourney-zitadel -c bootstrap -- env | grep ZITADEL_LOGIN_V2_BASE_URI`
for a stray `/ui/v2/login` suffix and re-run the bootstrap sidecar.
```

- [ ] **Step 3: Commit**

```bash
git add DEVELOPMENT.md
git commit -m "docs: update Zitadel login verification recipe for Login V2

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: Live staging verification (deploy + curl through Login V2)

**Files:** none (no repo changes — exercises Tasks 1-7's output against the real cluster).

**Interfaces:**
- Consumes: Task 5's two logged `client_id` lines, Task 7's documented recipe verbatim.
- Produces: pass/fail evidence for the PR description's test plan (issue #82's Login V2 scope addition; completes the curl verification Phase 15/#86 deferred).

- [ ] **Step 1: Deploy the branch to staging**

Follow `DEVELOPMENT.md`'s "Deploy workflow" (build/push images from this branch, then `helm upgrade --install` with the existing flags from Phase 15 — no new required flags, `zitadel.login.enabled` defaults to `true`).

- [ ] **Step 2: Confirm the login pod reaches Ready**

```bash
kubectl --context mcgee-local -n opentourney-staging get pods -l app.kubernetes.io/component=zitadel-login
```

Expected: one pod, `1/1 Running`. If it's stuck on the `wait-for-zitadel` init container, confirm core Zitadel's own pod is already `Running` first.

- [ ] **Step 3: Read the logged client_ids and confirm the feature was enabled**

```bash
kubectl --context mcgee-local -n opentourney-staging logs \
  deploy/opentourney-staging-opentourney-zitadel -c bootstrap | grep -E "client_id|Login V2"
```

Expected: three lines — `application 'opentourney-cli' client_id=...`, `application 'opentourney-frontend' client_id=...`, `Login V2 feature enabled, baseUri=...`.

- [ ] **Step 4: Confirm `/oauth/v2/authorize` redirects instead of 404ing**

```bash
kubectl --context mcgee-local -n opentourney-staging port-forward svc/zitadel 8080:8080 &
curl -s -o /dev/null -w "%{http_code}\n" --resolve zitadel.opentourney-staging.svc.cluster.local:8080:127.0.0.1 \
  "http://zitadel.opentourney-staging.svc.cluster.local:8080/oauth/v2/authorize?client_id=x&redirect_uri=http://localhost:8765/callback&response_type=code&scope=openid&code_challenge=x&code_challenge_method=S256"
```

Expected: a redirect status (`302`/`303`), not `404`. (The `client_id=x` is intentionally invalid — this step only checks that a login page exists to redirect to, not a full auth flow; Step 5 does the real flow with a valid `client_id`.)

- [ ] **Step 5: Run the full verification recipe from `DEVELOPMENT.md`**

Follow `DEVELOPMENT.md`'s "Verifying a real Zitadel login" section (Task 7) end to end: port-forward both services, PKCE authorize/login as `organizer@staging.local` through the real Login V2 page, token exchange, backend call.

Expected: backend responds `200` (not `401`) — confirms `identity_from_claims` accepts the `roles` and `source_system: "zitadel"` claims from a token obtained through a real Login V2 login, completing the check Phase 15/#86 deferred.

- [ ] **Step 6: Confirm no regression in existing unit tests**

```bash
cd backend && python -m pytest tests/unit/test_oidc.py -v
```

Expected: all existing cases pass unchanged (no backend code was touched).

- [ ] **Step 7: Record results**

Note the pass/fail outcome of Steps 2-6 in the PR description's test plan checklist. No commit — this task's deliverable is verification evidence, not a code change.
