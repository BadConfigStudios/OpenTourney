# Zitadel System API Domain Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register the in-cluster Service name (`zitadel`) as a real instance domain via Zitadel's System API, unblocking the backend's internal JWKS fetch (currently 404s — see spec's Context section for the full root-cause trace).

**Architecture:** Reuses the exact `SystemAPIUsers` X.509-JWT mechanism already live in this chart for Login V2 (`zitadel-system-api-users-configmap.yaml`, `genSelfSignedCert`-based keypair Secret with lookup-reuse-on-upgrade) — a second system user (`opentourney-bootstrap`, `SYSTEM_OWNER` role) added to the same config, trusted via a second chart-generated keypair. `bootstrap.py` signs a JWT-bearer assertion with the private half, exchanges it at `/oauth/v2/token` for a system-scoped access token, and calls `AddCustomDomain` with it instead of the wrong `AddTrustedDomain` call it currently makes.

> **Deviation (as-built):** the `/oauth/v2/token` exchange described above does not exist as a mechanism — commit `326d9fd` (same PR) fixed this after it failed live with `invalid_grant: invalid assertion`. The signed JWT is presented directly as the `Authorization: Bearer` value on the System API call; there is no token exchange step.

**Tech Stack:** Helm (`genSelfSignedCert` Sprig function, existing chart patterns), Python (`bootstrap.py` — adds `PyJWT[crypto]`), Zitadel Instance Service v2beta (`AddCustomDomain`) + OAuth2 JWT Bearer grant (RFC 7523).

## Global Constraints

- Zero backend application code changes (`backend/app/**` untouched) — confirmed in the spec, `RemoteJWKSProvider` already handles any RS256 issuer/audience/JWKS combination.
- `bootstrap.py` changes follow its existing idempotent get-or-create pattern (a confirmed-already-registered response is a no-op, not an error) — every resource in the file already does this.
- No secret/key material is ever written to a tracked file or CLI history — the keypair is chart-generated (`genSelfSignedCert`) and lives only in a k8s Secret, same as the existing Login V2 service key.
- `system.domain.write` is granted only by the built-in `SYSTEM_OWNER` role (confirmed in `cmd/defaults.yaml`'s `InternalAuthZ.RolePermissionMappings` at the deployed Zitadel version, v4.17.1) — no narrower built-in role exists for it.
- No unit-test infrastructure exists for `bootstrap.py` or this chart's templates — every task's verification is `helm lint`/`helm template` render checks and/or live cluster verification, matching every prior task in this same PR's ledger.

---

### Task 1: Bootstrap system-key Secret (RSA keypair)

**Files:**
- Create: `charts/opentourney/templates/zitadel-bootstrap-system-key-secret.yaml`

**Interfaces:**
- Consumes: `.Values.zitadel.enabled`, `ot.fullname`/`ot.labels` helpers (existing).
- Produces: Secret `<release>-zitadel-bootstrap-system-key` with keys `tls.crt` (public cert, consumed by Task 2's `SystemAPIUsers` config) and `tls.key` (private key, consumed by Task 2's deployment wiring and Task 3's `bootstrap.py`).

- [ ] **Step 1: Write the Secret template**

Create `charts/opentourney/templates/zitadel-bootstrap-system-key-secret.yaml`:

```yaml
{{- if .Values.zitadel.enabled }}
{{- $secretName := printf "%s-zitadel-bootstrap-system-key" (include "ot.fullname" .) }}
{{- $existing := lookup "v1" "Secret" .Release.Namespace $secretName }}
{{- if and $existing $existing.data (hasKey $existing.data "tls.crt") (hasKey $existing.data "tls.key") }}
# Reuse the existing keypair on upgrade -- a new cert on every `helm upgrade`
# would break core Zitadel's SystemAPIUsers trust of bootstrap.py's JWTs
# (Task 2) until both sides picked up the new cert simultaneously. Same
# reasoning as zitadel-login-secret.yaml's identical reuse block.
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
{{- $cert := genSelfSignedCert "bootstrap-system-key" nil (list "bootstrap-system-key") 3650 }}
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
  --set-string secrets.oidcJwksUrl=http://x \
  --set-string zitadel.masterkey=12345678901234567890123456789012 \
  --set-string zitadel.firstInstance.adminPassword='Abcdef1!' \
  | python3 -c "import sys, yaml; list(yaml.safe_load_all(sys.stdin))" \
  && echo RENDER_OK
```

Expected: `helm lint` reports 0 charts failed, `RENDER_OK` prints. Grep the raw `helm template` output for `zitadel-bootstrap-system-key` and confirm a single `Secret` with `type: kubernetes.io/tls` renders.

- [ ] **Step 3: Commit**

```bash
git add charts/opentourney/templates/zitadel-bootstrap-system-key-secret.yaml
git commit -m "feat(zitadel): generate bootstrap System API keypair

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Core trusts bootstrap as a SYSTEM_OWNER system user

**Files:**
- Modify: `charts/opentourney/templates/zitadel-system-api-users-configmap.yaml` (whole file)
- Modify: `charts/opentourney/templates/zitadel-deployment.yaml:23-33` (annotations)
- Modify: `charts/opentourney/templates/zitadel-deployment.yaml:46-84` (volumes, args, volumeMounts)
- Modify: `charts/opentourney/templates/zitadel-deployment.yaml:172-204` (bootstrap container: volumeMounts, env)

**Interfaces:**
- Consumes: Task 1's Secret (`<release>-zitadel-bootstrap-system-key`, both keys).
- Produces: core Zitadel accepts JWTs signed by `tls.key` as system user `opentourney-bootstrap` with role `SYSTEM_OWNER`; `bootstrap` container has the private key mounted at `/bootstrap-system-key/tls.key` and a new env var `ZITADEL_SYSTEM_API_AUDIENCE` — both consumed by Task 3.

- [ ] **Step 1: Decouple the `SystemAPIUsers` ConfigMap from `login.enabled`, add the bootstrap entry**

The existing ConfigMap only exists when Login V2 is enabled, but the bootstrap system user must exist regardless of whether Login V2 is (JWKS validation is independent of the login UI). Replace the whole file:

```yaml
{{- if .Values.zitadel.enabled }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "ot.fullname" . }}-zitadel-system-api-users
  labels:
    {{- include "ot.labels" . | nindent 4 }}
data:
  system-api-users.yaml: |
    SystemAPIUsers:
      opentourney-bootstrap:
        Path: /bootstrap-system-key/tls.crt
        Memberships:
          - MemberType: System
            Roles:
              - SYSTEM_OWNER
      {{- if .Values.zitadel.login.enabled }}
      login-client:
        Path: /login-client-cert/tls.crt
        Memberships:
          - MemberType: System
            Roles:
              - IAM_LOGIN_CLIENT
      {{- end }}
{{- end }}
```

- [ ] **Step 2: Make core always load `--config`, always mount the bootstrap cert; keep login-client mount login-gated**

In `charts/opentourney/templates/zitadel-deployment.yaml`, find (the `volumes:` through `containers:` opening, `zitadel` container's `args`/`volumeMounts`):

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

Replace with:

```yaml
      volumes:
        - name: pat
          emptyDir: {}
        - name: bootstrap-script
          configMap:
            name: {{ include "ot.fullname" . }}-zitadel-bootstrap
        - name: bootstrap-system-key-cert
          secret:
            secretName: {{ printf "%s-zitadel-bootstrap-system-key" (include "ot.fullname" .) }}
            items:
              - key: tls.crt
                path: tls.crt
        - name: system-api-users-config
          configMap:
            name: {{ include "ot.fullname" . }}-zitadel-system-api-users
        {{- if .Values.zitadel.login.enabled }}
        - name: login-client-cert
          secret:
            secretName: {{ printf "%s-zitadel-login-service-key" (include "ot.fullname" .) }}
            items:
              - key: tls.crt
                path: tls.crt
        {{- end }}
      containers:
        - name: zitadel
          image: "{{ .Values.zitadel.image.repository }}:{{ .Values.zitadel.image.tag }}"
          imagePullPolicy: {{ .Values.zitadel.image.pullPolicy }}
          args:
            - start-from-init
            - --masterkeyFromEnv
            - --config
            - /config/system-api-users.yaml
          volumeMounts:
            - name: pat
              mountPath: /pat
            - name: bootstrap-system-key-cert
              mountPath: /bootstrap-system-key
              readOnly: true
            - name: system-api-users-config
              mountPath: /config
              readOnly: true
            {{- if .Values.zitadel.login.enabled }}
            - name: login-client-cert
              mountPath: /login-client-cert
              readOnly: true
            {{- end }}
```

- [ ] **Step 3: Make the restart-checksum annotation unconditional**

Find (`zitadel-deployment.yaml:23-33`):

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

Replace with:

```yaml
      annotations:
        # Ties the pod template to the bootstrap script's content so a bootstrap.py edit
        # + `helm upgrade` actually restarts the pod and picks up the fix. Safe now that the
        # PAT is persisted to a Secret (see the "bootstrap" container below) rather than only
        # living in the emptyDir — a pod replacement no longer loses the one-shot credential.
        checksum/bootstrap-configmap: {{ include (print $.Template.BasePath "/zitadel-bootstrap-configmap.yaml") . | sha256sum }}
        # Same reasoning, for the SystemAPIUsers config -- core only re-reads --config
        # files on process start, so a content change needs a pod restart to take effect.
        # Unconditional now: the bootstrap system user (SYSTEM_OWNER) must exist
        # regardless of zitadel.login.enabled.
        checksum/system-api-users-configmap: {{ include (print $.Template.BasePath "/zitadel-system-api-users-configmap.yaml") . | sha256sum }}
```

- [ ] **Step 4: Mount the private key + add `ZITADEL_SYSTEM_API_AUDIENCE` into the `bootstrap` container**

Find (`zitadel-deployment.yaml:172-204`, the `bootstrap` container):

```yaml
        - name: bootstrap
          image: python:3.12-alpine
          # `;` before `sleep infinity`, not `&&`: the container must park after bootstrap.py
          # exits on EITHER path (success, or a wait_for_pat() timeout when already bootstrapped)
          # rather than exiting itself. A Deployment can't set restartPolicy per-container, so an
          # exiting container restart-loops forever, which keeps the pod's Ready condition false
          # and pulls it out of svc/zitadel's endpoints even though the zitadel container is healthy.
          command: ["sh", "-c", "pip install --no-cache-dir requests==2.32.3 && python /scripts/bootstrap.py; sleep infinity"]
          env:
            # Zitadel validates the request Host header against ZITADEL_EXTERNALDOMAIN
            # (anti-DNS-rebinding protection) and 404s otherwise. The sidecar connects
            # via localhost:8080 (same pod) but must still present the external domain
            # as the Host header for every Management API call.
            - name: ZITADEL_EXTERNAL_DOMAIN
              value: {{ .Values.zitadel.externalDomain | default (printf "zitadel.%s.svc.cluster.local" .Release.Namespace) | quote }}
            # Secret used to durably persist the FirstInstance-minted PAT beyond the emptyDir's
            # pod lifetime — see bootstrap.py's get_pat_from_secret()/save_pat_to_secret().
            - name: ZITADEL_PAT_SECRET_NAME
              value: {{ printf "%s-zitadel-pat" (include "ot.fullname" .) | quote }}
            {{- if .Values.zitadel.login.enabled }}
            - name: ZITADEL_LOGIN_V2_BASE_URI
              # publicBaseUri is an explicit opt-in override for environments that expose
              # Login V2 externally (e.g. a Cloudflare tunnel route) -- browser redirects
              # from core need a URI the browser can actually reach, unlike the in-cluster
              # default below. Empty by default: most deploys never need this.
              value: {{ .Values.zitadel.login.publicBaseUri | default (printf "http://%s-zitadel-login:3000" (include "ot.fullname" .)) | quote }}
            {{- end }}
          volumeMounts:
            - name: pat
              mountPath: /pat
            - name: bootstrap-script
              mountPath: /scripts
```

Replace with:

```yaml
        - name: bootstrap
          image: python:3.12-alpine
          # `;` before `sleep infinity`, not `&&`: the container must park after bootstrap.py
          # exits on EITHER path (success, or a wait_for_pat() timeout when already bootstrapped)
          # rather than exiting itself. A Deployment can't set restartPolicy per-container, so an
          # exiting container restart-loops forever, which keeps the pod's Ready condition false
          # and pulls it out of svc/zitadel's endpoints even though the zitadel container is healthy.
          command: ["sh", "-c", "pip install --no-cache-dir requests==2.32.3 'PyJWT[crypto]'==2.10.1 && python /scripts/bootstrap.py; sleep infinity"]
          env:
            # Zitadel validates the request Host header against ZITADEL_EXTERNALDOMAIN
            # (anti-DNS-rebinding protection) and 404s otherwise. The sidecar connects
            # via localhost:8080 (same pod) but must still present the external domain
            # as the Host header for every Management API call.
            - name: ZITADEL_EXTERNAL_DOMAIN
              value: {{ .Values.zitadel.externalDomain | default (printf "zitadel.%s.svc.cluster.local" .Release.Namespace) | quote }}
            # Secret used to durably persist the FirstInstance-minted PAT beyond the emptyDir's
            # pod lifetime — see bootstrap.py's get_pat_from_secret()/save_pat_to_secret().
            - name: ZITADEL_PAT_SECRET_NAME
              value: {{ printf "%s-zitadel-pat" (include "ot.fullname" .) | quote }}
            # Zitadel's system-JWT audience check requires an exact string match against
            # core's own external URL. Port is only appended when it isn't the scheme's
            # default -- identical logic to zitadel-login-configmap.yaml's AUDIENCE, which
            # this must match exactly since both are validated by the same core check
            # (confirmed live during Task 8 of the parent plan: a missing port on a
            # non-default port caused every call to 401 with "audience is not valid").
            {{- $extPort := int .Values.zitadel.externalPort }}
            {{- $extSecure := .Values.zitadel.externalSecure }}
            {{- $isDefaultPort := or (and $extSecure (eq $extPort 443)) (and (not $extSecure) (eq $extPort 80)) }}
            - name: ZITADEL_SYSTEM_API_AUDIENCE
              value: {{ printf "http%s://%s%s" (ternary "s" "" $extSecure) (.Values.zitadel.externalDomain | default (printf "zitadel.%s.svc.cluster.local" .Release.Namespace)) (ternary "" (printf ":%d" $extPort) $isDefaultPort) | quote }}
            {{- if .Values.zitadel.login.enabled }}
            - name: ZITADEL_LOGIN_V2_BASE_URI
              # publicBaseUri is an explicit opt-in override for environments that expose
              # Login V2 externally (e.g. a Cloudflare tunnel route) -- browser redirects
              # from core need a URI the browser can actually reach, unlike the in-cluster
              # default below. Empty by default: most deploys never need this.
              value: {{ .Values.zitadel.login.publicBaseUri | default (printf "http://%s-zitadel-login:3000" (include "ot.fullname" .)) | quote }}
            {{- end }}
          volumeMounts:
            - name: pat
              mountPath: /pat
            - name: bootstrap-script
              mountPath: /scripts
            - name: bootstrap-system-key
              mountPath: /bootstrap-system-key
              readOnly: true
```

- [ ] **Step 5: Add the private-key volume for the `bootstrap` container**

In the same `volumes:` block edited in Step 2, add one more entry (this one has no `login.enabled` guard — it's a separate Secret item, `tls.key`, only ever mounted into the `bootstrap` container, not `zitadel` core):

Find (now-edited `volumes:` block from Step 2, ending):

```yaml
        {{- if .Values.zitadel.login.enabled }}
        - name: login-client-cert
          secret:
            secretName: {{ printf "%s-zitadel-login-service-key" (include "ot.fullname" .) }}
            items:
              - key: tls.crt
                path: tls.crt
        {{- end }}
      containers:
```

Replace with:

```yaml
        {{- if .Values.zitadel.login.enabled }}
        - name: login-client-cert
          secret:
            secretName: {{ printf "%s-zitadel-login-service-key" (include "ot.fullname" .) }}
            items:
              - key: tls.crt
                path: tls.crt
        {{- end }}
        - name: bootstrap-system-key
          secret:
            secretName: {{ printf "%s-zitadel-bootstrap-system-key" (include "ot.fullname" .) }}
            items:
              - key: tls.key
                path: tls.key
      containers:
```

- [ ] **Step 6: Helm lint + template render**

Run the same render command as Task 1 Step 2. Expected: `RENDER_OK`; grep the output and confirm:
- `zitadel` container's `args` always includes `--config /config/system-api-users.yaml` (no `login.enabled` conditional left around it).
- `zitadel` container mounts `bootstrap-system-key-cert` at `/bootstrap-system-key`.
- `bootstrap` container mounts `bootstrap-system-key` at `/bootstrap-system-key` and has env var `ZITADEL_SYSTEM_API_AUDIENCE` set to `https://opentourney-staging.badconfig.com` (default-port form, matching `values.staging.yaml`'s `externalSecure=true`/`externalPort=443`).
- The rendered `system-api-users.yaml` ConfigMap data contains both `opentourney-bootstrap` (unconditional) and `login-client` (since `values.staging.yaml` has `login.enabled: true`) entries.

- [ ] **Step 7: Commit**

```bash
git add charts/opentourney/templates/zitadel-system-api-users-configmap.yaml \
        charts/opentourney/templates/zitadel-deployment.yaml
git commit -m "feat(zitadel): trust bootstrap.py as a SYSTEM_OWNER system user

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: `bootstrap.py` — sign System API JWT, call the real `AddCustomDomain`

> **Deviation (as-built):** `get_system_api_token()` does not exchange the assertion at `/oauth/v2/token` — see the Architecture note above. It returns the signed JWT itself, used directly as the Bearer token in `add_custom_domain`'s request (commit `326d9fd`).

**Files:**
- Modify: `charts/opentourney/files/bootstrap.py:33-40` (imports)
- Modify: `charts/opentourney/files/bootstrap.py:274-313` (`get_instance_id`/`add_trusted_domain` → `get_instance_id`/`get_system_api_token`/`add_custom_domain`)
- Modify: `charts/opentourney/files/bootstrap.py:518-520` (`main()` call site)

**Interfaces:**
- Consumes: Task 2's mounted private key (`/bootstrap-system-key/tls.key`) and env var `ZITADEL_SYSTEM_API_AUDIENCE`.
- Produces: `zitadel` (the internal Service name) registered as a real instance domain — Task 4's live JWKS curl depends on this.

- [ ] **Step 1: Add the `PyJWT` import**

Find (`bootstrap.py:33-39`):

```python
import base64
import os
import secrets
import string
import sys
import time

import requests
```

Replace with:

```python
import base64
import os
import secrets
import string
import sys
import time

import jwt
import requests
```

- [ ] **Step 2: Replace `add_trusted_domain` with `get_system_api_token` + `add_custom_domain`**

Find (`bootstrap.py:274-313`):

```python
def get_instance_id(session):
    response = session.get(f"{ZITADEL_BASE}/admin/v1/instances/me")
    response.raise_for_status()
    return response.json()["instance"]["id"]


def add_trusted_domain(session, instance_id, domain):
    # Trusted-domain registration lives under the v2beta Instance service, a
    # third base path in this file (alongside MGMT and the /v2 Feature API
    # above) -- not under /admin/v1, which has no such endpoint.
    #
    # Needed because a real Zitadel instance can only have one canonical
    # externalDomain, which has to be the public hostname (so core's own
    # anti-DNS-rebinding check and Login V2's server-generated redirects work
    # for a real external browser -- confirmed live during Task 8
    # verification). In-cluster callers (this backend's JWKS fetch,
    # notably) still need to reach Zitadel via the internal Service name
    # without round-tripping through the public internet (which hits
    # Cloudflare's bot/TLS-fingerprint block, error 1010, against a plain
    # HTTP client). AddTrustedDomain lets both hostnames pass the same
    # Host-header check without weakening it.
    #
    # Domain matching strips the port before comparing (Zitadel's
    # DomainCtx.InstanceDomain()), so the registered value must be the bare
    # hostname -- "zitadel", not "zitadel:8080".
    response = session.post(
        f"{ZITADEL_BASE}/v2beta/instances/{instance_id}/trusted-domains",
        json={"domain": domain},
    )
    # Zitadel returns this as 400 (FAILED_PRECONDITION), not 409 -- same
    # underlying domain-uniqueness check as the primary/generated domain.
    if response.status_code == 400 and "Errors.Instance.Domain.AlreadyExists" in response.text:
        return  # already trusted -- idempotent no-op
    if not response.ok:
        print(
            f"POST /v2beta/instances/{instance_id}/trusted-domains -> {response.status_code}: {response.text}",
            file=sys.stderr,
        )
    response.raise_for_status()
```

Replace with:

```python
def get_instance_id(session):
    response = session.get(f"{ZITADEL_BASE}/admin/v1/instances/me")
    response.raise_for_status()
    return response.json()["instance"]["id"]


SYSTEM_API_USER = "opentourney-bootstrap"
SYSTEM_API_KEY_PATH = "/bootstrap-system-key/tls.key"
SYSTEM_API_AUDIENCE = os.environ["ZITADEL_SYSTEM_API_AUDIENCE"]


def get_system_api_token():
    # System API auth is separate from the PAT used everywhere else in this
    # file: a JWT-bearer assertion (RFC 7523), signed with the private half
    # of the keypair core trusts via SystemAPIUsers (see
    # charts/opentourney/templates/zitadel-system-api-users-configmap.yaml).
    # Needed because AddCustomDomain (below) requires the `system.domain.write`
    # permission, which only the built-in SYSTEM_OWNER role grants -- the PAT's
    # IAM_OWNER-equivalent role (used for every other call in this file)
    # doesn't have it. Confirmed live: the PAT gets 403 AUTH-5mWD2 on this
    # specific endpoint.
    with open(SYSTEM_API_KEY_PATH) as f:
        private_key = f.read()
    now = int(time.time())
    assertion = jwt.encode(
        {
            "iss": SYSTEM_API_USER,
            "sub": SYSTEM_API_USER,
            "aud": SYSTEM_API_AUDIENCE,
            "iat": now,
            "exp": now + 300,
        },
        private_key,
        algorithm="RS256",
    )
    # Not the shared `session` -- this exchange carries no PAT Authorization
    # header and needs form encoding, not JSON. Still needs the same Host
    # header spoof every other call in this file uses (anti-DNS-rebinding).
    response = requests.post(
        f"{ZITADEL_BASE}/oauth/v2/token",
        headers={"Host": ZITADEL_EXTERNAL_DOMAIN},
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
            "scope": "openid",
        },
    )
    if not response.ok:
        print(f"POST /oauth/v2/token (system API) -> {response.status_code}: {response.text}", file=sys.stderr)
    response.raise_for_status()
    return response.json()["access_token"]


def add_custom_domain(instance_id, domain, system_api_token):
    # The real endpoint for registering a Host-matchable instance domain --
    # AddTrustedDomain (this file's previous approach) is an unrelated
    # mechanism; its gRPC handler calls a different command than the one
    # Zitadel's Host-check (query.InstanceByHost) actually reads from.
    #
    # Needed because a real Zitadel instance can only have one canonical
    # externalDomain, which has to be the public hostname (so core's own
    # anti-DNS-rebinding check and Login V2's server-generated redirects work
    # for a real external browser -- confirmed live during Task 8
    # verification). In-cluster callers (this backend's JWKS fetch,
    # notably) still need to reach Zitadel via the internal Service name
    # without round-tripping through the public internet (which hits
    # Cloudflare's bot/TLS-fingerprint block, error 1010, against a plain
    # HTTP client).
    #
    # Domain matching strips the port before comparing (Zitadel's
    # DomainCtx.InstanceDomain()), so the registered value must be the bare
    # hostname -- "zitadel", not "zitadel:8080".
    response = requests.post(
        f"{ZITADEL_BASE}/v2beta/instances/{instance_id}/custom-domains",
        headers={
            "Host": ZITADEL_EXTERNAL_DOMAIN,
            "Authorization": f"Bearer {system_api_token}",
        },
        json={"domain": domain},
    )
    # Matched on message text, not status code: AddCustomDomain's command
    # (internal/command/instance_domain.go) throws AlreadyExists (gRPC code 6,
    # conventionally -> HTTP 409) for this case, a different error type than
    # AddTrustedDomain's FailedPrecondition (code 9 -> 400) seen live for the
    # unrelated old endpoint -- not yet live-confirmed for this endpoint, so
    # don't gate on a guessed status code twice in one file.
    if not response.ok and "Errors.Instance.Domain.AlreadyExists" in response.text:
        return  # already registered -- idempotent no-op
    if not response.ok:
        print(
            f"POST /v2beta/instances/{instance_id}/custom-domains -> {response.status_code}: {response.text}",
            file=sys.stderr,
        )
    response.raise_for_status()
```

- [ ] **Step 3: Update the `main()` call site**

Find (`bootstrap.py:518-520`):

```python
    instance_id = get_instance_id(session)
    add_trusted_domain(session, instance_id, "zitadel")
    print("trusted domain 'zitadel' added (lets in-cluster callers use the internal Service name)")
```

Replace with:

```python
    instance_id = get_instance_id(session)
    system_api_token = get_system_api_token()
    add_custom_domain(instance_id, "zitadel", system_api_token)
    print("instance domain 'zitadel' added (lets in-cluster callers use the internal Service name)")
```

- [ ] **Step 4: Syntax check**

Run: `python3 -m py_compile charts/opentourney/files/bootstrap.py`
Expected: no output, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add charts/opentourney/files/bootstrap.py
git commit -m "fix(zitadel): register instance domain via System API AddCustomDomain

Replaces the previous AddTrustedDomain call, which hit an unrelated
mechanism (confirmed via source read of zitadel/zitadel v4.17.1) and
never actually satisfied the Host-check AddCustomDomain does.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: Live staging verification

**Files:** none (deploy + verify only)

**Interfaces:**
- Consumes: Tasks 1-3, deployed together.
- Produces: confirmation the backend's internal JWKS path works; no regression to the existing public-domain browser login flow.

- [ ] **Step 1: Redeploy with the full known-working flag set**

Run (from repo root, `mcgee-local` context — matches every prior deploy this session):

```bash
./scripts/staging-upgrade.sh \
  --set-string ingress.enabled=true \
  --set-string ingress.hostname=opentourney-staging.badconfig.com \
  --set-string zitadel.externalDomain=opentourney-staging.badconfig.com \
  --set-string zitadel.externalSecure=true \
  --set-string zitadel.externalPort=443 \
  --set-string zitadel.login.publicBaseUri=https://opentourney-staging.badconfig.com/ui/v2/login \
  --set-string secrets.oidcIssuer=https://opentourney-staging.badconfig.com \
  --set-string secrets.oidcJwksUrl=http://zitadel:8080/oauth/v2/keys
```

Expected: `STATUS: deployed`, new Helm revision number.

- [ ] **Step 2: Wait for the new `zitadel` pod, confirm it's 2/2 Ready**

```bash
kubectl --context mcgee-local -n opentourney-staging get pods | grep opentourney-zitadel- | grep -v login
```

Expected: exactly one `opentourney-zitadel-<hash>-<hash>` pod, `2/2 Running`, low `AGE` (new pod from this rollout — the old one should be `Terminating` or already gone).

- [ ] **Step 3: Tail the `bootstrap` sidecar log for a clean run**

```bash
kubectl --context mcgee-local -n opentourney-staging logs <new-pod-name> -c bootstrap | tail -20
```

Expected: log ends with `instance domain 'zitadel' added (lets in-cluster callers use the internal Service name)` followed by `roles-claim action attached to both Complement Token triggers` and `bootstrap complete` — no traceback.

- [ ] **Step 4: Curl the internal JWKS URL from a throwaway debug pod**

```bash
kubectl --context mcgee-local run jwks-debug --rm -i --restart=Never --image=curlimages/curl -n opentourney-staging -- -sv http://zitadel:8080/oauth/v2/keys
```

Expected: `HTTP/1.1 200 OK` (not 404), body is a JSON object with a `keys` array (real JWKS content, not the `unable to set instance` error text).

- [ ] **Step 5: Regression check — confirm the public-domain login flow still works**

This task's chart edits touched shared `zitadel-deployment.yaml`/`zitadel-system-api-users-configmap.yaml` gating logic, so confirm Login V2 wasn't broken:

```bash
kubectl --context mcgee-local run authorize-check --rm -i --restart=Never --image=curlimages/curl -n opentourney-staging -- \
  -s -o /dev/null -w "%{http_code} %{redirect_url}\n" \
  "https://opentourney-staging.badconfig.com/oauth/v2/authorize?client_id=386717021196255263&redirect_uri=http://localhost/callback&response_type=code&scope=openid"
```

Expected: `302` status, `redirect_url` pointing at `https://opentourney-staging.badconfig.com/ui/v2/login/...` (same shape confirmed working in the parent plan's Task 8) — not a 404 or 500.

- [ ] **Step 6: Update the SDD ledger**

Append to `.superpowers/sdd/2026-08-17-phase16-pr1-login-v2-infra/progress.md`:

```
Post-Task-8 follow-up (System API domain registration, spec:
docs/superpowers/specs/2026-08-18-zitadel-system-api-domain-registration-design.md,
plan: docs/superpowers/plans/2026-08-18-zitadel-system-api-domain-registration.md):
  - Root-caused two failed live fix attempts (AddTrustedDomain is an unrelated
    mechanism; AddCustomDomain needs system.domain.write, which the PAT's role
    lacks) via direct source read of zitadel/zitadel v4.17.1.
  - Implemented: chart-generated SYSTEM_OWNER system-API keypair (reusing the
    exact SystemAPIUsers/genSelfSignedCert pattern already used for Login V2),
    bootstrap.py signs a JWT-bearer assertion and calls the real AddCustomDomain.
  - RESOLVED live: internal JWKS fetch (http://zitadel:8080/oauth/v2/keys)
    returns 200 with real key material. Public-domain login flow regression-
    checked, still working.
  - Current live deploy: revision <fill in from Step 1's helm output>.
```

- [ ] **Step 7: Commit the ledger update**

```bash
git add .superpowers/sdd/2026-08-17-phase16-pr1-login-v2-infra/progress.md
git commit -m "docs(ledger): record System API domain registration fix, resolved live

Co-Authored-By: Claude <noreply@anthropic.com>"
```
