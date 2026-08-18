# Phase 16 Infra Fix PR (issue #88 blockers #1-3 + minors) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 3 infra issues from issue #88 that block Phase 16 PR2's manual staging login walkthrough (`publicBaseUri` misdocumentation, a stale non-self-healing OIDC redirect URI, missing ingress routes), plus 4 low-LOE cleanup items from the same review pass — all before PR2 (frontend `oidc-client-ts` integration) starts.

**Architecture:** Chart-only + one Python script change, no frontend code. Each fix is independently verifiable via `helm lint`/`helm template`; end-to-end correctness (does a real browser login actually work) is only checkable via one consolidated live staging deploy + walkthrough in the final task, matching this chart's existing verification convention (no automated test suite exists for Helm templates or `bootstrap.py`).

**Tech Stack:** Helm, Python 3 (`bootstrap.py`, stdlib + `requests`/`PyJWT` only), Zitadel Management API v1.

## Global Constraints

- No frontend code changes — this PR is strictly `charts/opentourney/` + `DEVELOPMENT.md`.
- Every chart edit must keep `helm lint charts/opentourney` and the `helm template` render (Task 6's command) clean before that task's commit.
- Follow this file's own established idempotency conventions exactly: `api_post()`'s 409-as-no-op, and the "no changes returns 400 not 200" quirk already documented on `set_trigger()`/`get_or_create_action()` — don't invent a different pattern.
- `docs/superpowers/specs/2026-08-18-phase16-infra-fixes-design.md` is the approved spec; this plan implements it in full. Items #4, minor #7, minor #10, and minor #11 from issue #88 are explicitly out of scope (see spec's "Explicitly out of scope").

---

### Task 1: Fix the `publicBaseUri` "bare host" misdocumentation (issue #88 #1)

**Files:**
- Modify: `charts/opentourney/values.yaml` (comment above `zitadel.login.publicBaseUri`)
- Modify: `charts/opentourney/files/bootstrap.py` (comment above `LOGIN_V2_BASE_URI`)
- Modify: `charts/opentourney/templates/zitadel-deployment.yaml` (in-cluster fallback default)
- Modify: `DEVELOPMENT.md` (the "double `/ui/v2/login`" troubleshooting note)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — this task only corrects comments/a fallback string; no function signatures or chart values change shape. Task 6's live login walkthrough depends on the corrected fallback behavior (not directly exercised on staging, since `values.staging.yaml` already overrides `publicBaseUri`, but a future deploy without the override now gets the working shape by default).

- [ ] **Step 1: Correct the `values.yaml` comment**

In `charts/opentourney/values.yaml`, find:

```yaml
    # Opt-in override for environments where Login V2 is exposed externally
    # (e.g. a Cloudflare tunnel route pointed at it) -- unset means core
    # redirects browsers to the in-cluster-only Service address, which only
    # works for curl/port-forward-based verification, not a real browser.
    # Same origin as the frontend and core Zitadel (see the top-level
    # `ingress` block below) -- no in-cluster/public identity split, so
    # Login V2's own server-generated redirects (which bake in
    # ZITADEL_EXTERNALDOMAIN directly, not just the inbound request Host)
    # resolve correctly for a real browser instead of pointing at an
    # unreachable internal hostname.
    publicBaseUri: ""
```

Replace with:

```yaml
    # Opt-in override for environments where Login V2 is exposed externally
    # (e.g. a Cloudflare tunnel route pointed at it) -- unset means core
    # redirects browsers to the in-cluster-only Service address, which only
    # works for curl/port-forward-based verification, not a real browser.
    # Same origin as the frontend and core Zitadel (see the top-level
    # `ingress` block below) -- no in-cluster/public identity split, so
    # Login V2's own server-generated redirects (which bake in
    # ZITADEL_EXTERNALDOMAIN directly, not just the inbound request Host)
    # resolve correctly for a real browser instead of pointing at an
    # unreachable internal hostname.
    # MUST include the `/ui/v2/login` suffix (e.g.
    # "https://host/ui/v2/login") -- an earlier version of this comment
    # claimed Zitadel's defaultBaseURL() appends the suffix itself and a bare
    # host was correct. That was never live-verified; the only configuration
    # ever confirmed working end-to-end (values.staging.yaml) uses the
    # suffixed form, and a bare host produces a 404 on login (issue #88 #1).
    publicBaseUri: ""
```

- [ ] **Step 2: Correct the `bootstrap.py` comment**

In `charts/opentourney/files/bootstrap.py`, find:

```python
# In-cluster Service DNS name for the Login V2 deployment (see
# charts/opentourney/templates/zitadel-login-service.yaml). Bare host only --
# Zitadel's defaultBaseURL() appends /ui/v2/login itself; a pre-suffixed value
# here produces a double path. Unset (None) when zitadel.login.enabled=false --
# enable_login_v2_feature() must not run in that case (see main()).
LOGIN_V2_BASE_URI = os.environ.get("ZITADEL_LOGIN_V2_BASE_URI")
```

Replace with:

```python
# In-cluster Service DNS name for the Login V2 deployment (see
# charts/opentourney/templates/zitadel-login-service.yaml), MUST include the
# /ui/v2/login suffix -- the only value ever confirmed working live
# (values.staging.yaml's publicBaseUri override) is fully suffixed; an
# earlier claim that Zitadel's defaultBaseURL() appends the suffix itself
# was never live-verified and produced a 404 (issue #88 #1). Set by the
# chart (zitadel-deployment.yaml) to always include the suffix, whether
# using the default in-cluster fallback or an operator override. Unset
# (None) when zitadel.login.enabled=false -- enable_login_v2_feature() must
# not run in that case (see main()).
LOGIN_V2_BASE_URI = os.environ.get("ZITADEL_LOGIN_V2_BASE_URI")
```

- [ ] **Step 3: Append the suffix to the in-cluster fallback default**

In `charts/opentourney/templates/zitadel-deployment.yaml`, find:

```yaml
            {{- if .Values.zitadel.login.enabled }}
            - name: ZITADEL_LOGIN_V2_BASE_URI
              # publicBaseUri is an explicit opt-in override for environments that expose
              # Login V2 externally (e.g. a Cloudflare tunnel route) -- browser redirects
              # from core need a URI the browser can actually reach, unlike the in-cluster
              # default below. Empty by default: most deploys never need this.
              value: {{ .Values.zitadel.login.publicBaseUri | default (printf "http://%s-zitadel-login:3000" (include "ot.fullname" .)) | quote }}
            {{- end }}
```

Replace with:

```yaml
            {{- if .Values.zitadel.login.enabled }}
            - name: ZITADEL_LOGIN_V2_BASE_URI
              # publicBaseUri is an explicit opt-in override for environments that expose
              # Login V2 externally (e.g. a Cloudflare tunnel route) -- browser redirects
              # from core need a URI the browser can actually reach, unlike the in-cluster
              # default below. Empty by default: most deploys never need this.
              # Both branches include the /ui/v2/login suffix -- the only shape ever
              # confirmed working live (issue #88 #1); a bare host 404s.
              value: {{ .Values.zitadel.login.publicBaseUri | default (printf "http://%s-zitadel-login:3000/ui/v2/login" (include "ot.fullname" .)) | quote }}
            {{- end }}
```

- [ ] **Step 4: Correct the `DEVELOPMENT.md` troubleshooting note**

In `DEVELOPMENT.md`, find:

```
**Troubleshooting a double `/ui/v2/login/ui/v2/login` redirect:** the
bootstrap sidecar's `enable_login_v2_feature()` sets `loginV2.baseUri` to
the bare login-service host (`http://<release>-zitadel-login:3000`) --
Zitadel's `defaultBaseURL()` appends `/ui/v2/login` itself. If the browser
lands on a doubled path, check
`kubectl -n opentourney-staging exec deploy/opentourney-staging-opentourney-zitadel -c bootstrap -- env | grep ZITADEL_LOGIN_V2_BASE_URI`
for a stray `/ui/v2/login` suffix and re-run the bootstrap sidecar.
```

Replace with:

```
**Troubleshooting a login redirect 404:** `loginV2.baseUri` (set by the
bootstrap sidecar's `enable_login_v2_feature()`) MUST include the
`/ui/v2/login` suffix, both for the in-cluster default
(`http://<release>-zitadel-login:3000/ui/v2/login`) and any
`zitadel.login.publicBaseUri` override -- a bare host without the suffix
produces a 404 on login (issue #88 #1; a prior version of this note
incorrectly claimed the suffix was appended automatically and should be
omitted here). If login 404s, check
`kubectl -n opentourney-staging exec deploy/opentourney-staging-opentourney-zitadel -c bootstrap -- env | grep ZITADEL_LOGIN_V2_BASE_URI`
for a missing `/ui/v2/login` suffix and re-run the bootstrap sidecar.
```

- [ ] **Step 5: Helm lint + template render**

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

Expected: `RENDER_OK`; grep the output for `ZITADEL_LOGIN_V2_BASE_URI` and confirm it renders `https://opentourney-staging.badconfig.com/ui/v2/login` (from `values.staging.yaml`'s existing override — unchanged by this task, confirms the override path still works).

- [ ] **Step 6: Commit**

```bash
git add charts/opentourney/values.yaml charts/opentourney/files/bootstrap.py \
        charts/opentourney/templates/zitadel-deployment.yaml DEVELOPMENT.md
git commit -m "fix(zitadel): publicBaseUri must include /ui/v2/login, not a bare host

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Parameterize the frontend redirect URI + self-heal on redeploy (issue #88 #2)

**Files:**
- Modify: `charts/opentourney/files/bootstrap.py`
- Modify: `charts/opentourney/templates/zitadel-deployment.yaml`
- Modify: `DEVELOPMENT.md` (the devMode troubleshooting note)

**Interfaces:**
- Consumes: `ot.zitadelOrigin` helper (`charts/opentourney/templates/_helpers.tpl`, unchanged) — composes `scheme://domain[:port]` from `secure`/`port`/`domain` dict keys.
- Produces: `ZITADEL_FRONTEND_APP_REDIRECT_URI` env var on the `bootstrap` container, consumed by `bootstrap.py`'s `FRONTEND_APP_REDIRECT_URI` constant. `get_or_create_application()`'s signature is unchanged, but its already-exists branch now PUTs before returning — every caller (only `main()`) is unaffected.

- [ ] **Step 1: Compute and pass the redirect URI from the chart**

In `charts/opentourney/templates/zitadel-deployment.yaml`, find:

```yaml
            {{- if .Values.zitadel.login.enabled }}
            - name: ZITADEL_LOGIN_V2_BASE_URI
              # publicBaseUri is an explicit opt-in override for environments that expose
              # Login V2 externally (e.g. a Cloudflare tunnel route) -- browser redirects
              # from core need a URI the browser can actually reach, unlike the in-cluster
              # default below. Empty by default: most deploys never need this.
              # Both branches include the /ui/v2/login suffix -- the only shape ever
              # confirmed working live (issue #88 #1); a bare host 404s.
              value: {{ .Values.zitadel.login.publicBaseUri | default (printf "http://%s-zitadel-login:3000/ui/v2/login" (include "ot.fullname" .)) | quote }}
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

Replace with:

```yaml
            {{- if .Values.zitadel.login.enabled }}
            - name: ZITADEL_LOGIN_V2_BASE_URI
              # publicBaseUri is an explicit opt-in override for environments that expose
              # Login V2 externally (e.g. a Cloudflare tunnel route) -- browser redirects
              # from core need a URI the browser can actually reach, unlike the in-cluster
              # default below. Empty by default: most deploys never need this.
              # Both branches include the /ui/v2/login suffix -- the only shape ever
              # confirmed working live (issue #88 #1); a bare host 404s.
              value: {{ .Values.zitadel.login.publicBaseUri | default (printf "http://%s-zitadel-login:3000/ui/v2/login" (include "ot.fullname" .)) | quote }}
            {{- end }}
            # opentourney-frontend's registered OIDC redirect URI (bootstrap.py). The
            # frontend and Zitadel deliberately share one public origin (see
            # gateway-ingress.yaml's single-hostname routing) -- reusing
            # zitadel.externalSecure/externalPort for scheme/port is safe because the
            # fail guard in gateway-ingress.yaml (issue #88 minor #8) requires
            # ingress.hostname to equal zitadel.externalDomain whenever both are set.
            - name: ZITADEL_FRONTEND_APP_REDIRECT_URI
              value: {{ printf "%s/callback" (include "ot.zitadelOrigin" (dict "secure" .Values.zitadel.externalSecure "port" .Values.zitadel.externalPort "domain" (required "ingress.hostname is required to register opentourney-frontend's OIDC redirect URI" .Values.ingress.hostname))) | quote }}
          volumeMounts:
            - name: pat
              mountPath: /pat
            - name: bootstrap-script
              mountPath: /scripts
            - name: bootstrap-system-key
              mountPath: /bootstrap-system-key
              readOnly: true
```

- [ ] **Step 2: Read the URI from the environment instead of hardcoding it**

In `charts/opentourney/files/bootstrap.py`, find:

```python
FRONTEND_APP_NAME = "opentourney-frontend"
# The frontend's actual origin varies per environment (staging vs. a future
# prod). Kept as a single staging-hardcoded value for now, matching this
# chart's existing scope (opentourney-staging only) -- revisit if/when a
# second environment needs its own app registration.
FRONTEND_APP_REDIRECT_URI = "http://opentourney-staging.local/callback"
```

Replace with:

```python
FRONTEND_APP_NAME = "opentourney-frontend"
# Computed by the chart from ingress.hostname + zitadel.externalSecure/externalPort
# (see zitadel-deployment.yaml) -- varies per environment, and must exactly match
# what the real frontend's AuthContext sends as its redirect_uri (Phase 16 PR2's
# `${window.location.origin}/callback`) or Zitadel rejects the authorize call.
FRONTEND_APP_REDIRECT_URI = os.environ["ZITADEL_FRONTEND_APP_REDIRECT_URI"]
```

- [ ] **Step 3: Self-heal the already-registered app's redirect URI on every run**

In `charts/opentourney/files/bootstrap.py`, find:

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

    # Unlike every other get-or-create in this file, an OIDC app's redirect_uris is
    # exactly the field that changes across bootstrap.py edits (issue #88 #2: this
    # PR's own FRONTEND_APP_REDIRECT_URI fix) -- a stale already-registered app would
    # otherwise keep rejecting the real client's callback forever. PUT the current
    # config back on every run, the same self-healing pattern get_or_create_action()
    # already uses for its ACTION_SOURCE script.
    update_body = {
        "redirectUris": redirect_uris,
        "responseTypes": body["responseTypes"],
        "grantTypes": body["grantTypes"],
        "authMethodType": body["authMethodType"],
        "accessTokenType": body["accessTokenType"],
    }
    put_response = session.put(
        f"{MGMT}/projects/{project_id}/apps/{app_id}/oidc_config", json=update_body
    )
    if put_response.status_code == 400:
        # Same "No Changes" idempotency quirk documented on set_trigger()/
        # get_or_create_action() -- PUTting back byte-identical config Zitadel
        # already has returns 400, not a 200 no-op. UpdateOIDCAppConfig's own
        # error id for this case isn't yet confirmed live (unlike COMMAND-Nfh52/
        # ACTION-dg4t2 for the other two) -- matching on code==9 (gRPC
        # FailedPrecondition, the shared family both known ids belong to) is
        # deliberately broader here until a real run confirms the specific id;
        # if this ever masks a genuine error, the printed stderr line below
        # still surfaces it for a human, since raise_for_status() only fires on
        # a *different* status code, not on a 400 matched here.
        try:
            put_body = put_response.json()
        except ValueError:
            put_body = {}
        if put_body.get("code") != 9:
            print(
                f"PUT /projects/{project_id}/apps/{app_id}/oidc_config -> 400: {put_response.text}",
                file=sys.stderr,
            )
            put_response.raise_for_status()
    elif not put_response.ok:
        print(
            f"PUT /projects/{project_id}/apps/{app_id}/oidc_config -> {put_response.status_code}: {put_response.text}",
            file=sys.stderr,
        )
        put_response.raise_for_status()

    detail = session.get(f"{MGMT}/projects/{project_id}/apps/{app_id}")
    detail.raise_for_status()
    return detail.json()["app"]["oidcConfig"]["clientId"]
```

- [ ] **Step 4: Correct the `DEVELOPMENT.md` devMode note**

In `DEVELOPMENT.md`, find:

```
**Troubleshooting the authorize call:** if Zitadel rejects the redirect URI
outright (400 on step 3, before any login page renders), the client likely
needs `"devMode": true` added to `get_or_create_application()`'s request
body -- Zitadel's default posture requires HTTPS redirect URIs for
non-loopback apps, and this deployment (`ZITADEL_EXTERNALSECURE=false`)
runs entirely over HTTP. Add the field, re-run the bootstrap Job/pod
restart, and retry.
```

Replace with:

```
**Troubleshooting the authorize call:** if Zitadel rejects the redirect URI
outright (400 on step 3, before any login page renders), the client likely
needs `"devMode": true` added to `get_or_create_application()`'s request
body -- Zitadel's default posture requires HTTPS redirect URIs for
non-loopback apps. Staging runs `zitadel.externalSecure: true` and the
frontend's redirect URI is HTTPS (issue #88 #2), so this shouldn't be
needed there; this note previously (incorrectly, for staging) assumed an
HTTP-only deployment. If it does trigger, add the field to `body` in both
`get_or_create_application()`'s create path and its `update_body` (the
self-healing PUT), re-run the bootstrap Job/pod restart, and retry.
```

- [ ] **Step 5: Helm lint + template render**

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

Expected: `RENDER_OK`; grep the output for `ZITADEL_FRONTEND_APP_REDIRECT_URI` and confirm it renders `https://opentourney-staging.badconfig.com/callback`.

- [ ] **Step 6: Confirm no bare `ingress.hostname`-less render breaks**

```bash
helm template opentourney-staging charts/opentourney \
  --set zitadel.enabled=false \
  | python3 -c "import sys, yaml; list(yaml.safe_load_all(sys.stdin))" \
  && echo RENDER_OK
```

Expected: `RENDER_OK` — with `zitadel.enabled=false`, the whole `zitadel-deployment.yaml` template (including the new `required` guard) is skipped by its outer `{{- if .Values.zitadel.enabled }}`, so this must still render cleanly with no `ingress.hostname` set.

- [ ] **Step 7: Commit**

```bash
git add charts/opentourney/files/bootstrap.py charts/opentourney/templates/zitadel-deployment.yaml DEVELOPMENT.md
git commit -m "fix(zitadel): parameterize frontend redirect URI, self-heal on redeploy

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Route `/oidc`, `/idps`, `/v2` to core Zitadel (issue #88 #3)

**Files:**
- Modify: `charts/opentourney/templates/gateway-ingress.yaml`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — additive ingress rules only. PR2's `oidc-client-ts` (a later PR) depends on `/oidc/v1/userinfo` and `/oidc/v1/end_session` actually reaching core Zitadel instead of the frontend's SPA catch-all.

- [ ] **Step 1: Add the three routes**

In `charts/opentourney/templates/gateway-ingress.yaml`, find:

```yaml
          {{- if .Values.zitadel.enabled }}
          # Core Zitadel's own endpoints -- OIDC discovery, JWKS, authorize/token.
          - path: /oauth
            pathType: Prefix
            backend:
              service:
                name: zitadel
                port:
                  number: 8080
          - path: /.well-known
            pathType: Prefix
            backend:
              service:
                name: zitadel
                port:
                  number: 8080
          {{- end }}
```

Replace with:

```yaml
          {{- if .Values.zitadel.enabled }}
          # Core Zitadel's own endpoints -- OIDC discovery, JWKS, authorize/token,
          # userinfo/end_session (/oidc), external IdP callbacks (/idps), and the v2
          # gRPC-gateway API (/v2, e.g. features/instance). Without these, requests
          # fall through to the frontend's SPA catch-all and get a 200 with the SPA
          # shell instead of a real 404 from Zitadel (issue #88 #3) -- silently
          # breaking oidc-client-ts's userinfo/end_session calls (Phase 16 PR2).
          - path: /oauth
            pathType: Prefix
            backend:
              service:
                name: zitadel
                port:
                  number: 8080
          - path: /.well-known
            pathType: Prefix
            backend:
              service:
                name: zitadel
                port:
                  number: 8080
          - path: /oidc
            pathType: Prefix
            backend:
              service:
                name: zitadel
                port:
                  number: 8080
          - path: /idps
            pathType: Prefix
            backend:
              service:
                name: zitadel
                port:
                  number: 8080
          - path: /v2
            pathType: Prefix
            backend:
              service:
                name: zitadel
                port:
                  number: 8080
          {{- end }}
```

- [ ] **Step 2: Helm lint + template render**

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

Expected: `RENDER_OK`; grep the output for `path: /oidc`, `path: /idps`, `path: /v2` and confirm all three route to `service: name: zitadel`.

- [ ] **Step 3: Commit**

```bash
git add charts/opentourney/templates/gateway-ingress.yaml
git commit -m "fix(ingress): route /oidc, /idps, /v2 to core Zitadel

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: Low-LOE minors — `enableServiceLinks`, hostname/domain guard, constant placement (#6, #8, #9)

**Files:**
- Modify: `charts/opentourney/templates/zitadel-login-deployment.yaml`
- Modify: `charts/opentourney/templates/gateway-ingress.yaml`
- Modify: `charts/opentourney/files/bootstrap.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — a defensive pod setting, a chart-render-time guard, and a pure code-motion refactor. No behavior change on an already-correctly-configured deploy (`values.staging.yaml` already sets matching `ingress.hostname`/`zitadel.externalDomain`).

- [ ] **Step 1 (#6): Add `enableServiceLinks: false` to the login deployment**

In `charts/opentourney/templates/zitadel-login-deployment.yaml`, find:

```yaml
    spec:
      {{- with .Values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      initContainers:
```

Replace with:

```yaml
    spec:
      # Same reasoning as core's Deployment (zitadel-deployment.yaml): this pod
      # receives the same injected ZITADEL_* env vars and reads ZITADEL_EXTERNALDOMAIN
      # too, so it's exposed to the same kubelet service-links collision risk.
      enableServiceLinks: false
      {{- with .Values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      initContainers:
```

- [ ] **Step 2 (#8): Guard `ingress.hostname` against `zitadel.externalDomain` mismatch**

In `charts/opentourney/templates/gateway-ingress.yaml`, find:

```yaml
{{- if .Values.ingress.enabled }}
{{- if not .Values.ingress.hostname }}
{{- fail "ingress.hostname is required when ingress.enabled=true" }}
{{- end }}
```

Replace with:

```yaml
{{- if .Values.ingress.enabled }}
{{- if not .Values.ingress.hostname }}
{{- fail "ingress.hostname is required when ingress.enabled=true" }}
{{- end }}
{{- if and .Values.zitadel.enabled .Values.zitadel.externalDomain (ne .Values.ingress.hostname .Values.zitadel.externalDomain) }}
{{- fail "ingress.hostname must equal zitadel.externalDomain when both are set -- Zitadel's anti-DNS-rebinding Host check 404s on any mismatch (this failure mode has already been debugged twice on this chart)" }}
{{- end }}
```

- [ ] **Step 3 (#9): Move the System API constants to the top of `bootstrap.py`**

In `charts/opentourney/files/bootstrap.py`, find:

```python
def get_instance_id(session):
    response = session.get(f"{ZITADEL_BASE}/admin/v1/instances/me")
    response.raise_for_status()
    return response.json()["instance"]["id"]


SYSTEM_API_USER = "opentourney-bootstrap"
SYSTEM_API_KEY_PATH = "/bootstrap-system-key/tls.key"
SYSTEM_API_AUDIENCE = os.environ["ZITADEL_SYSTEM_API_AUDIENCE"]


def get_system_api_token():
```

Replace with:

```python
def get_instance_id(session):
    response = session.get(f"{ZITADEL_BASE}/admin/v1/instances/me")
    response.raise_for_status()
    return response.json()["instance"]["id"]


def get_system_api_token():
```

Then find the module-level constants block:

```python
PAT_PATH = "/pat/pat.txt"
ROLES = ["organizer", "scorekeeper", "player"]
PROJECT_NAME = "OpenTourney"
ACTION_NAME = "addRolesClaim"
CLI_APP_NAME = "opentourney-cli"
```

Replace with:

```python
PAT_PATH = "/pat/pat.txt"
ROLES = ["organizer", "scorekeeper", "player"]
PROJECT_NAME = "OpenTourney"
ACTION_NAME = "addRolesClaim"
CLI_APP_NAME = "opentourney-cli"
SYSTEM_API_USER = "opentourney-bootstrap"
SYSTEM_API_KEY_PATH = "/bootstrap-system-key/tls.key"
SYSTEM_API_AUDIENCE = os.environ["ZITADEL_SYSTEM_API_AUDIENCE"]
```

- [ ] **Step 4: Confirm the move didn't break ordering**

```bash
cd /Users/bkcrisler/Documents/GitHub/OpenTourney
python3 -c "import ast; ast.parse(open('charts/opentourney/files/bootstrap.py').read())"
grep -n "^SYSTEM_API_USER\|^SYSTEM_API_KEY_PATH\|^SYSTEM_API_AUDIENCE\|^def get_system_api_token" charts/opentourney/files/bootstrap.py
```

Expected: `ast.parse` prints nothing (valid syntax); the `grep` shows the three constants appearing once, before `def get_system_api_token`, and no longer between `get_instance_id` and `get_system_api_token`.

- [ ] **Step 5: Helm lint + template render**

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

Expected: `RENDER_OK`; grep the output for `enableServiceLinks: false` under the `zitadel-login` Deployment's `spec.template.spec`.

- [ ] **Step 6: Confirm the new #8 guard actually fails on a mismatch**

```bash
helm template opentourney-staging charts/opentourney \
  -f charts/opentourney/values.staging.yaml \
  --set zitadel.externalDomain=wrong.example.com \
  --set-string secrets.databaseUrl=postgres://x \
  --set-string secrets.oidcIssuer=http://x \
  --set-string secrets.oidcAudience=x \
  --set-string secrets.oidcJwksStatic='{"keys":[]}' \
  --set-string zitadel.masterkey=12345678901234567890123456789012 \
  --set-string zitadel.firstInstance.adminPassword='Abcdef1!' \
  2>&1 | grep -q "must equal zitadel.externalDomain" && echo GUARD_FIRED
```

Expected: `GUARD_FIRED`.

- [ ] **Step 7: Commit**

```bash
git add charts/opentourney/templates/zitadel-login-deployment.yaml \
        charts/opentourney/templates/gateway-ingress.yaml \
        charts/opentourney/files/bootstrap.py
git commit -m "chore(zitadel): enableServiceLinks on login pod, hostname/domain guard, tidy constants

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: `DEVELOPMENT.md` — real staging URL, point at `staging-upgrade.sh` (issue #88 #5)

**Files:**
- Modify: `DEVELOPMENT.md`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — documentation only.

- [ ] **Step 1: Replace the "Public URL: TBD" line**

In `DEVELOPMENT.md`, find:

```
- Public URL: TBD — no Cloudflare Tunnel hostname is assigned yet. Until one
  exists, reach the deployment via `kubectl port-forward`.
```

Replace with:

```
- Public URL: `https://opentourney-staging.badconfig.com` (Cloudflare Tunnel
  → the chart's `gateway-ingress.yaml`, path-routed to the frontend, core
  Zitadel, and Login V2 — see `values.staging.yaml`'s `ingress`/`zitadel`
  blocks). `kubectl port-forward` still works as a fallback (e.g. bypassing
  the tunnel to isolate an ingress-vs-backend issue).
```

- [ ] **Step 2: Point the deploy workflow at `scripts/staging-upgrade.sh`**

In `DEVELOPMENT.md`, find:

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
   (`kubectl --context mcgee-local -n opentourney-staging logs deploy/opentourney-staging-opentourney-zitadel -c bootstrap`).
```

Replace with:

```
3. **Deploy/update the release** — once the release already exists (true for
   `opentourney-staging` today), prefer `scripts/staging-upgrade.sh`: it
   pulls `secrets.databaseUrl`/`oidcAudience`/`oidcIssuer`/`oidcJwksUrl` and
   the Zitadel masterkey/admin password straight from the live cluster's own
   Secrets instead of re-pasting them by hand, and reuses whatever image
   tags are currently deployed unless overridden:

   ```bash
   scripts/staging-upgrade.sh \
     --set-string backend.image.tag=<tag> \
     --set-string frontend.image.tag=<tag> \
     --set-string docs.image.tag=<tag>
   ```

   Extra flags win over the script's own (Helm applies later `--set`/
   `--set-string` flags last) — e.g. `--set-string secrets.oidcAudience=<new-client-id>`
   after registering a new app.

   For a *fresh* namespace stand-up (the script's `secret` lookups would
   fail — nothing exists yet), fall back to the full manual command instead:

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

   `<zitadel-issuer>` is `values.staging.yaml`'s committed
   `secrets.oidcIssuer`, `https://opentourney-staging.badconfig.com` — public
   now (Phase 16 PR1), not in-cluster-only as an earlier version of this
   section described.
   `<client-id-from-bootstrap-log>` comes from the Zitadel bootstrap
   sidecar's own log line, `application 'opentourney-cli' client_id=...`
   (`kubectl --context mcgee-local -n opentourney-staging logs deploy/opentourney-staging-opentourney-zitadel -c bootstrap`)
   — the frontend app's client_id is logged the same way, one line down,
   `application 'opentourney-frontend' client_id=...`.
```

- [ ] **Step 3: Commit**

```bash
git add DEVELOPMENT.md
git commit -m "docs: point staging deploy workflow at scripts/staging-upgrade.sh, real public URL

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: Deploy to staging, live verification

**Files:** none (deploy + manual verification only; no commit at the end unless a fix is needed, in which case loop back to the relevant task above).

**Interfaces:**
- Consumes: every prior task's chart/script changes, deployed together.
- Produces: pass/fail verification evidence for this PR's description.

- [ ] **Step 0: Confirm which `kubectl` context is live**

You (the owner) are currently remote/off-network for this session. Before running any `kubectl`/`helm upgrade`/`scripts/staging-upgrade.sh` command below:

```bash
kubectl --context mcgee-local get ns opentourney-staging
```

Expected: either succeeds (use `mcgee-local` for every command below), or times out — if it times out, use `mcgee-remote` for every command below instead (`scripts/staging-upgrade.sh` hardcodes `CONTEXT=mcgee-local`; if `mcgee-remote` is needed, either edit that line locally for this run — don't commit the edit — or run the equivalent manual `helm upgrade --kube-context mcgee-remote ...` instead of the script).

- [ ] **Step 1: Build and push images**

Only the chart and `bootstrap.py` changed in this PR — no `backend`/`frontend`/`docs` Dockerfile or source changes. Skip the image build/push steps; redeploy the chart against whatever image tags are already live (confirm via `helm --kube-context <context> -n opentourney-staging get values opentourney-staging -o json | python3 -c "import sys,json; v=json.load(sys.stdin); print(v['backend']['image']['tag'], v['frontend']['image']['tag'], v['docs']['image']['tag'])"`).

- [ ] **Step 2: Deploy**

```bash
scripts/staging-upgrade.sh
```

(No extra flags needed — image tags default to what's already deployed, per Step 1.)

Expected: `helm upgrade` completes with `STATUS: deployed`.

- [ ] **Step 3: Confirm the bootstrap sidecar ran clean and self-healed the redirect URI**

```bash
kubectl --context <context> -n opentourney-staging logs deploy/opentourney-staging-opentourney-zitadel -c bootstrap --tail=50
```

Expected: `application 'opentourney-frontend' client_id=...` printed with no preceding stack trace; no `PUT .../oidc_config -> 4` error lines (a 400 with `code: 9` is fine and expected on a byte-identical re-run — see Task 2 Step 3 — but any other status or code means Step 3's self-heal PUT needs a fix, loop back to Task 2 before continuing).

- [ ] **Step 4: Confirm the new ingress routes reach core Zitadel**

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://opentourney-staging.badconfig.com/oidc/v1/userinfo
curl -s -o /dev/null -w "%{http_code}\n" https://opentourney-staging.badconfig.com/v2/features/instance
```

Expected: neither returns `200` with an HTML body (the frontend's `index.html`) — `/oidc/v1/userinfo` unauthenticated should be `401`; `/v2/features/instance` (a `PUT`-only endpoint per `enable_login_v2_feature()`) should be `404` or `405` on a bare `GET`, not `200`. If either returns `200`, `curl -s https://opentourney-staging.badconfig.com/oidc/v1/userinfo` and confirm the body isn't the frontend's `<!doctype html>` shell before concluding the route is broken (a `200` with a real Zitadel JSON error body is also acceptable evidence the route reached Zitadel).

- [ ] **Step 5: Drive one real browser login end-to-end**

1. Open `https://opentourney-staging.badconfig.com/oauth/v2/authorize?client_id=<opentourney-cli-client-id-from-bootstrap-log>&redirect_uri=http://localhost:8765/callback&response_type=code&scope=openid%20profile%20email&code_challenge=<pkce-challenge>&code_challenge_method=S256` (reuse `DEVELOPMENT.md`'s "Verifying a real Zitadel login" PKCE-generation snippet for `<pkce-challenge>`) in a browser.
2. Expect a redirect to `https://opentourney-staging.badconfig.com/ui/v2/login/...` (Login V2's real page, not a 404) — confirms Task 1's `publicBaseUri` fix.
3. Log in as `organizer@staging.local` (password from the bootstrap sidecar's log, Step 3 above).
4. Expect a redirect to `http://localhost:8765/callback?code=...` (a browser "can't connect" page is fine — nothing listens on that port; what matters is the URL, not a successful connection) — confirms the registered redirect URI now matches (Task 2's fix) and no `devMode` 400 occurred before this point.

Expected: all 4 sub-steps pass. If step 2 404s, Task 1's fix is incomplete — loop back. If step 3 rejects the redirect URI with a 400 before the login page even renders, Task 2's devMode assumption was wrong — add `"devMode": true` per Task 2 Step 4's already-updated `DEVELOPMENT.md` note, to both `get_or_create_application()`'s create `body` and its `update_body`, redeploy, and retry.

- [ ] **Step 6: Record results**

Note the pass/fail outcome of Steps 3-5 in the PR description's test plan checklist. No commit for this task unless Step 5 uncovered a real bug — in that case, fix it under the relevant task above (Task 1 or 2) with a new commit, then re-run Steps 2-5.
