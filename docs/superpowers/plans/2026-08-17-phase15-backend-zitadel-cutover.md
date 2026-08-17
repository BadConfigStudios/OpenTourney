# Phase 15 — Staging Backend Cutover to Zitadel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register a real OIDC client in Zitadel's staging instance and cut the backend's Helm secret over to Zitadel's real issuer/audience/JWKS, verified with a token from an actual Zitadel login.

**Architecture:** `charts/opentourney/files/bootstrap.py` (Zitadel's bootstrap sidecar) gains an idempotent step that registers a public Native OIDC client with JWT access tokens. `DEVELOPMENT.md`'s documented deploy command swaps the static-JWKS flag for Zitadel-derived issuer/audience/JWKS-URL flags. No backend application code changes — `RemoteJWKSProvider` and `decode_token` already validate any RS256 issuer/audience/JWKS combination.

**Tech Stack:** Python (bootstrap sidecar, `requests` only), Helm/Zitadel Management API v1 (REST/JSON), `kubectl`, `curl`.

## Global Constraints

- Zero backend application code changes (`backend/app/**` untouched) — per the design's core premise, `RemoteJWKSProvider` already handles any real issuer.
- `bootstrap.py` changes must follow its existing idempotent get-or-create pattern (treat 409 as no-op, resolve existing resource via search) — every other resource in the file already does this.
- OIDC app: type Native, `accessTokenType: OIDC_TOKEN_TYPE_JWT` (mandatory — Zitadel's default is opaque and the backend cannot validate it), `authMethodType: OIDC_AUTH_METHOD_TYPE_NONE` (public client, PKCE, no secret), redirect URI `http://localhost:8765/callback`.
- Client ID/audience wiring is manual (owner-approved during brainstorming): bootstrap.py logs `client_id`, operator passes it to `helm upgrade --set-string secrets.oidcAudience=<client_id>`. No `secretKeyRef` self-wiring in this phase.
- `secret.yaml` template requires no changes — it already branches on `oidcJwksUrl` vs `oidcJwksStatic`.

---

### Task 1: Register OIDC client in bootstrap.py

**Files:**
- Modify: `charts/opentourney/files/bootstrap.py:49-51` (constants)
- Modify: `charts/opentourney/files/bootstrap.py:194-197` (new function)
- Modify: `charts/opentourney/files/bootstrap.py:364-366` (wire into `main()`)

**Interfaces:**
- Consumes: `api_post(session, path, json_body)` (existing helper, `bootstrap.py:148`), `MGMT` constant (existing, `bootstrap.py:42`), `PROJECT_NAME`/`ROLES`/`ACTION_NAME` constants (existing, `bootstrap.py:49-51`).
- Produces: `get_or_create_application(session, project_id) -> str` returning the OIDC client's `client_id`. Task 2 and Task 3 rely on this being logged to stdout as `application {APP_NAME!r} client_id={client_id}`.

- [ ] **Step 1: Add `APP_NAME` and `APP_REDIRECT_URI` constants**

In `charts/opentourney/files/bootstrap.py`, find:

```python
ROLES = ["organizer", "scorekeeper", "player"]
PROJECT_NAME = "OpenTourney"
ACTION_NAME = "addRolesClaim"
```

Replace with:

```python
ROLES = ["organizer", "scorekeeper", "player"]
PROJECT_NAME = "OpenTourney"
ACTION_NAME = "addRolesClaim"
APP_NAME = "opentourney-cli"
# Nothing listens on this port. The Authorization Code lands in the browser's
# address bar as a 404 on redirect; it's copied out manually for the curl token
# exchange (see DEVELOPMENT.md's "Verifying a real Zitadel login" section).
APP_REDIRECT_URI = "http://localhost:8765/callback"
```

- [ ] **Step 2: Add `get_or_create_application()`**

Find:

```python
    # Nothing downstream needs the role's own ID, only its roleKey string.


def find_user_by_username(session, username):
```

Replace with:

```python
    # Nothing downstream needs the role's own ID, only its roleKey string.


def get_or_create_application(session, project_id):
    body = {
        "name": APP_NAME,
        "redirectUris": [APP_REDIRECT_URI],
        "responseTypes": ["OIDC_RESPONSE_TYPE_CODE"],
        "grantTypes": ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"],
        # Public client (no secret) using PKCE, matching both this phase's manual
        # curl-based Authorization Code flow and the frontend's future oidc-client-ts
        # integration (Phase 16) -- same client type/flow, no throwaway app to replace.
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


def find_user_by_username(session, username):
```

- [ ] **Step 3: Wire the new function into `main()`**

Find:

```python
    for role in ROLES:
        ensure_role(session, project_id, role)
    print(f"roles ensured: {ROLES}")

    for role in ROLES:
        user_id = get_or_create_user(session, role)
```

Replace with:

```python
    for role in ROLES:
        ensure_role(session, project_id, role)
    print(f"roles ensured: {ROLES}")

    client_id = get_or_create_application(session, project_id)
    # Logged unconditionally (unlike test-user passwords, which are unrecoverable
    # after creation) since client_id is retrievable via the Management API on any
    # later run -- this line is a convenience for copy/paste into the next
    # `helm upgrade --set-string secrets.oidcAudience=<client_id>`, not the only
    # source of truth.
    print(f"application {APP_NAME!r} client_id={client_id}")

    for role in ROLES:
        user_id = get_or_create_user(session, role)
```

- [ ] **Step 4: Local syntax check**

Run: `python3 -m py_compile charts/opentourney/files/bootstrap.py`
Expected: exits 0, no output.

- [ ] **Step 5: Helm render sanity check**

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

Expected: `helm lint` reports 0 charts failed; the template pipeline prints `RENDER_OK` (proves the edited `bootstrap.py` still embeds as valid YAML inside the ConfigMap — a broken indent would otherwise surface as a YAML parse error here).

- [ ] **Step 6: Commit**

```bash
git add charts/opentourney/files/bootstrap.py
git commit -m "feat(zitadel): register OIDC native client in bootstrap sidecar

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Update deploy docs

**Files:**
- Modify: `DEVELOPMENT.md:126-153` (deploy command + explanation)
- Modify: `DEVELOPMENT.md` (new section after the "Deploy workflow" section, i.e. after current line 169)

**Interfaces:**
- Consumes: `client_id` logged by Task 1's `get_or_create_application()` (referenced in prose, not machine-consumed).
- Produces: none (documentation only; Task 3 follows this doc's recipe verbatim).

- [ ] **Step 1: Swap the static-JWKS flag for Zitadel-derived flags**

In `DEVELOPMENT.md`, find:

```
   helm upgrade --install opentourney-staging charts/opentourney \
     --namespace opentourney-staging --create-namespace \
     -f charts/opentourney/values.staging.yaml \
     --set backend.image.tag=<tag> \
     --set frontend.image.tag=<tag> \
     --set docs.image.tag=<tag> \
     --set-string secrets.databaseUrl=<database-url> \
     --set-string secrets.oidcIssuer=<oidc-issuer> \
     --set-string secrets.oidcAudience=<oidc-audience> \
     --set-string secrets.oidcJwksStatic=<oidc-jwks-static-json> \
     --set-string zitadel.masterkey=<32-char-masterkey> \
     --set-string zitadel.firstInstance.adminPassword=<admin-password>
   ```

   `secrets.databaseUrl`, `secrets.oidcIssuer`, and `secrets.oidcAudience`
   are required (see Prerequisites above) — the chart's `required` guard on
   `secrets.databaseUrl` makes an unset/typo'd value fail the `helm upgrade`
   itself rather than silently deploying a broken release. Use
   `--set-string secrets.oidcJwksUrl=<oidc-jwks-url>` instead of
   `secrets.oidcJwksStatic` if the issuer's JWKS should be fetched live
   rather than pinned. `zitadel.masterkey` and
```

Replace with:

```
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
   `<client-id-from-bootstrap-log>` comes from the Zitadel bootstrap
   sidecar's own log line, `application 'opentourney-cli' client_id=...`
   (`kubectl -n opentourney-staging logs deploy/opentourney-staging-opentourney-zitadel -c bootstrap`).

   **Ordering gotcha, same shape as the masterkey caveat below:** on a
   *fresh* Zitadel stand-up, the client doesn't exist until after Zitadel's
   pod comes up and its bootstrap sidecar runs — so `secrets.oidcAudience`
   can't be correct on the very first `helm upgrade` in a new namespace.
   Deploy once, read the logged `client_id`, then `helm upgrade` again with
   `secrets.oidcAudience` set correctly. Because `get_or_create_application()`
   is idempotent, ordinary re-deploys against an already-bootstrapped
   instance never hit this — only a full teardown/rebuild does. `zitadel.masterkey` and
```

- [ ] **Step 2: Add the verification recipe**

In `DEVELOPMENT.md`, find the end of the "Deploy workflow" section — the block ending in:

```
   ```bash
   kubectl --context mcgee-local -n opentourney-staging set image \
     deployment/opentourney-staging-opentourney-backend backend=ghcr.io/badconfigstudios/opentourney/backend:<tag>
   kubectl --context mcgee-local -n opentourney-staging rollout status deployment/opentourney-staging-opentourney-backend
   ```
```

Replace with:

```
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

6. Call the backend with it:

   ```bash
   curl -s -H "Authorization: Bearer <access_token>" \
     http://<backend-staging-url>/events
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
```

- [ ] **Step 3: Commit**

```bash
git add DEVELOPMENT.md
git commit -m "docs: document Zitadel OIDC deploy flags and login verification recipe

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Live staging verification

**Files:** none (no repo changes — this task exercises Task 1 + Task 2's output against the real cluster).

**Interfaces:**
- Consumes: Task 1's `get_or_create_application()` (via its logged `client_id`), Task 2's documented recipe verbatim.
- Produces: pass/fail evidence for the PR description's test plan (issue #81's "verified via curl" acceptance criterion; closes PR #84's documented known-gap).

- [ ] **Step 1: Deploy the branch to staging**

Follow `DEVELOPMENT.md`'s "Deploy workflow" (build/push images from this
branch, then the `helm upgrade --install` command from Task 2 Step 1) —
first pass, `secrets.oidcAudience` will be a placeholder since the client
doesn't exist yet on a fresh instance, or reuse the existing `client_id` if
Zitadel is already bootstrapped from Phase 14 (`get_or_create_application()`
is idempotent, so this may already be a no-op re-run).

- [ ] **Step 2: Read the logged `client_id`**

```bash
kubectl --context mcgee-local -n opentourney-staging logs \
  deploy/opentourney-staging-opentourney-zitadel -c bootstrap | grep client_id
```

Expected: one line, `application 'opentourney-cli' client_id=<some-id>`.

- [ ] **Step 3: Re-deploy with the real audience**

Re-run the `helm upgrade` command with `secrets.oidcAudience=<client_id
from Step 2>` and `secrets.oidcIssuer`/`secrets.oidcJwksUrl` pointed at
Zitadel per Task 2's documented values.

- [ ] **Step 4: Run the verification recipe**

Follow `DEVELOPMENT.md`'s "Verifying a real Zitadel login" section
(Task 2 Step 2) end to end: port-forward, PKCE authorize/login as
`organizer@staging.local`, token exchange, backend call.

Expected: backend responds `200` (not `401`) — confirms `identity_from_claims`
accepted the `roles` and `source_system: "zitadel"` claims from a real
token, matching `backend/app/auth/identity.py`'s existing expectations.

- [ ] **Step 5: Confirm no regression in existing unit tests**

```bash
cd backend && python -m pytest tests/unit/test_oidc.py -v
```

Expected: all existing cases pass unchanged (no backend code was touched,
so this is a regression check, not new coverage).

- [ ] **Step 6: Record results**

Note the pass/fail outcome of Steps 4-5 in the PR description's test plan
checklist. No commit — this task's deliverable is verification evidence,
not a code change.
