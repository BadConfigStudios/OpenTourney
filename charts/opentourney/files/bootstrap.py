#!/usr/bin/env python3
"""
One-shot bootstrap sidecar for the Zitadel Deployment.

Runs once per Pod start against Zitadel's Management API (using the PAT
minted by Zitadel's own FirstInstance bootstrap, written to /pat/pat.txt):

  - creates the "OpenTourney" project
  - creates 3 project roles: organizer, scorekeeper, player
  - creates 3 human test users (organizer@staging.local, etc.), each with a
    freshly generated password (logged once, at creation time, to this
    container's stdout -- never written to a file, never committed to git)
  - grants each user their matching role
  - creates a Complement Token Action that flattens the user's grants into a
    `roles` claim, sets a fixed `source_system: "zitadel"` claim (required by
    `identity_from_claims`), and attaches it to both Complement Token triggers

Idempotent: every create call treats a 409 ("already exists") response as a
no-op success, then resolves the existing resource's ID via a _search call
so re-running this script (e.g. on every Pod restart / helm upgrade) is safe.

PAT durability: Zitadel's FirstInstance bootstrap that mints the PAT at
/pat/pat.txt only ever runs once per Postgres backing store — any pod
replacement after that first run permanently loses the PAT with no recovery
short of a database reset. To make pod restarts safe, this script persists
the PAT to a Kubernetes Secret (name in ZITADEL_PAT_SECRET_NAME) on first
successful acquisition, via the Kubernetes API server reachable in-cluster
through the ServiceAccount token/CA mounted at
/var/run/secrets/kubernetes.io/serviceaccount/, and checks that Secret
before ever waiting on the emptyDir file again.
"""
import base64
import os
import secrets
import string
import sys
import time

import jwt
import requests

ZITADEL_BASE = "http://localhost:8080"
MGMT = f"{ZITADEL_BASE}/management/v1"
# In-cluster Service DNS name for the Login V2 deployment (see
# charts/opentourney/templates/zitadel-login-service.yaml). Bare host only --
# Zitadel's defaultBaseURL() appends /ui/v2/login itself; a pre-suffixed value
# here produces a double path. Unset (None) when zitadel.login.enabled=false --
# enable_login_v2_feature() must not run in that case (see main()).
LOGIN_V2_BASE_URI = os.environ.get("ZITADEL_LOGIN_V2_BASE_URI")
# Zitadel validates the Host header against ZITADEL_EXTERNALDOMAIN (anti-DNS-rebinding
# protection) and returns 404 for any request presenting a different Host — including
# the "localhost:8080" the requests library would otherwise send by default when hitting
# this same-pod address. Every request must carry the external domain as its Host header.
ZITADEL_EXTERNAL_DOMAIN = os.environ["ZITADEL_EXTERNAL_DOMAIN"]
PAT_PATH = "/pat/pat.txt"
ROLES = ["organizer", "scorekeeper", "player"]
PROJECT_NAME = "OpenTourney"
ACTION_NAME = "addRolesClaim"
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

# --- PAT persistence (Kubernetes Secret) -----------------------------------------------
SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
K8S_API = "https://{}:{}".format(
    os.environ.get("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc"),
    os.environ.get("KUBERNETES_SERVICE_PORT", "443"),
)
PAT_SECRET_NAME = os.environ["ZITADEL_PAT_SECRET_NAME"]
PAT_SECRET_KEY = "pat"

ACTION_SOURCE = """
function addRolesClaim(ctx, api) {
  let roles = [];
  // ctx.v1.user.grants (and its own nested .grants) can be undefined -- not just
  // empty -- confirmed live via a real browser login: Zitadel's own official
  // custom_roles.js example guards this same way. Without the guard, a user
  // with any grants missing from this particular token request crashes the
  // whole Complement Token flow with a 500 (OIDC-AhX2u), not just an empty roles claim.
  if (ctx.v1.user.grants && ctx.v1.user.grants.grants) {
    ctx.v1.user.grants.grants.forEach(function (grant) {
      grant.roles.forEach(function (role) {
        roles.push(role);
      });
    });
  }
  api.v1.claims.setClaim("roles", roles);
  // identity_from_claims (backend/app/auth/identity.py) requires both "sub" and
  // "source_system" claims -- source_system is part of the composite key every
  // OrganizationMember/PodRole grant is keyed on. Without this, every request
  // 401s regardless of the roles claim above.
  api.v1.claims.setClaim("source_system", "zitadel");
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


def _k8s_session():
    """A requests.Session authenticated as this pod's ServiceAccount, talking
    directly to the in-cluster Kubernetes API server (no client library — matches
    this script's existing plain-`requests` footprint)."""
    session = requests.Session()
    with open(f"{SA_DIR}/token") as f:
        token = f.read().strip()
    session.headers["Authorization"] = f"Bearer {token}"
    session.verify = f"{SA_DIR}/ca.crt"
    return session


def _k8s_namespace():
    with open(f"{SA_DIR}/namespace") as f:
        return f.read().strip()


def _pat_secret_url(namespace):
    return f"{K8S_API}/api/v1/namespaces/{namespace}/secrets/{PAT_SECRET_NAME}"


def get_pat_from_secret():
    """Returns the PAT from the persisted Secret, or None if it doesn't exist yet
    (true-first-run case, or a pre-fix instance that never got one)."""
    session = _k8s_session()
    response = session.get(_pat_secret_url(_k8s_namespace()))
    if response.status_code == 404:
        return None
    response.raise_for_status()
    encoded = response.json().get("data", {}).get(PAT_SECRET_KEY)
    if not encoded:
        return None
    return base64.b64decode(encoded).decode().strip()


def save_pat_to_secret(pat):
    """Persists the PAT to a Secret so future pod restarts never need Zitadel's
    one-shot FirstInstance bootstrap to re-run."""
    session = _k8s_session()
    namespace = _k8s_namespace()
    body = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": PAT_SECRET_NAME},
        "type": "Opaque",
        "data": {PAT_SECRET_KEY: base64.b64encode(pat.encode()).decode()},
    }
    response = session.post(
        f"{K8S_API}/api/v1/namespaces/{namespace}/secrets", json=body
    )
    if response.status_code == 409:
        # Created concurrently (or by a previous partial run) — update in place instead.
        response = session.put(_pat_secret_url(namespace), json=body)
    response.raise_for_status()


def api_post(session, path, json_body):
    response = session.post(f"{MGMT}{path}", json=json_body)
    if response.status_code == 409:
        return None  # already exists — idempotent no-op
    if not response.ok:
        # Zitadel's gRPC-gateway error bodies name the offending field directly.
        print(f"POST {path} -> {response.status_code}: {response.text}", file=sys.stderr)
    response.raise_for_status()
    return response.json()


def generate_password():
    # Zitadel's default complexity policy: 8+ chars, upper, lower, digit, symbol.
    alphabet_lower = string.ascii_lowercase
    alphabet_upper = string.ascii_uppercase
    digits = string.digits
    symbols = "!@#$%^&*-_="
    parts = [
        secrets.choice(alphabet_upper),
        secrets.choice(alphabet_lower),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]
    parts += [secrets.choice(alphabet_lower + alphabet_upper + digits) for _ in range(8)]
    secrets.SystemRandom().shuffle(parts)
    return "".join(parts)


def get_or_create_project(session):
    result = api_post(session, "/projects", {"name": PROJECT_NAME})
    if result is not None:
        return result["id"]
    response = session.post(f"{MGMT}/projects/_search", json={})
    response.raise_for_status()
    for project in response.json().get("result", []):
        if project.get("name") == PROJECT_NAME:
            return project["id"]
    raise RuntimeError(f"project {PROJECT_NAME!r} 409'd on create but not found in search")


def ensure_role(session, project_id, role):
    api_post(
        session,
        f"/projects/{project_id}/roles",
        {"roleKey": role, "displayName": role.capitalize()},
    )
    # Nothing downstream needs the role's own ID, only its roleKey string.


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


def get_instance_id(session):
    response = session.get(f"{ZITADEL_BASE}/admin/v1/instances/me")
    response.raise_for_status()
    return response.json()["instance"]["id"]


SYSTEM_API_USER = "opentourney-bootstrap"
SYSTEM_API_KEY_PATH = "/bootstrap-system-key/tls.key"
SYSTEM_API_AUDIENCE = os.environ["ZITADEL_SYSTEM_API_AUDIENCE"]


def get_system_api_token():
    # System API auth is separate from the PAT used everywhere else in this
    # file, and separate from a normal OAuth2 JWT-bearer grant too -- no
    # token exchange happens. Zitadel's request-authorization path
    # (internal/api/authz/context.go's VerifyTokenAndCreateCtxData) tries the
    # Bearer value as a real access token first, and on failure falls back to
    # verifying it directly as a self-signed JWT assertion against the
    # SystemAPIUsers config (see
    # charts/opentourney/templates/zitadel-system-api-users-configmap.yaml) --
    # confirmed by reading that function and internal/api/authz/system_token.go
    # directly, after POSTing this same assertion to /oauth/v2/token (the
    # normal OAuth2 JWT-bearer grant flow) failed live with
    # "invalid_grant: invalid assertion" / "Errors.AuthNKey.NotFound": that
    # endpoint is Zitadel's unrelated *database-registered machine user* key
    # flow, not the System API's static-config one. The signed JWT itself
    # *is* the Bearer token; nothing to exchange it for.
    #
    # Needed because AddCustomDomain (below) requires the `system.domain.write`
    # permission, which only the built-in SYSTEM_OWNER role grants -- the PAT's
    # IAM_OWNER-equivalent role (used for every other call in this file)
    # doesn't have it. Confirmed live: the PAT gets 403 AUTH-5mWD2 on this
    # specific endpoint.
    with open(SYSTEM_API_KEY_PATH) as f:
        private_key = f.read()
    now = int(time.time())
    return jwt.encode(
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


def find_user_by_username(session, username):
    response = session.post(
        f"{MGMT}/users/_search",
        json={
            "queries": [
                {
                    "userNameQuery": {
                        "userName": username,
                        "method": "TEXT_QUERY_METHOD_EQUALS",
                    }
                }
            ]
        },
    )
    if response.status_code == 400:
        # Fall back to listing everything and filtering client-side.
        response = session.post(f"{MGMT}/users/_search", json={})
        response.raise_for_status()
        for user in response.json().get("result", []):
            if user.get("userName") == username:
                return user
        return None
    response.raise_for_status()
    results = response.json().get("result", [])
    return results[0] if results else None


def get_or_create_user(session, role):
    # The generated password is printed to stdout only on the create path (below) —
    # a 409/already-exists re-run prints nothing, since the password isn't retrievable
    # from Zitadel after creation. If a test user's logged password is lost (log scrolled
    # away, container restarted before it was captured), it is NOT recoverable from logs;
    # reset it via the Zitadel Console (using the FirstInstance admin credentials) instead.
    username = f"{role}@staging.local"
    password = generate_password()
    body = {
        "userName": username,
        "profile": {"firstName": role.capitalize(), "lastName": "Test"},
        "email": {"email": username, "isEmailVerified": True},
        "initialPassword": password,
    }
    result = api_post(session, "/users/human", body)
    if result is not None:
        print(f"created user {username} (id={result['userId']}); initial password logged once below")
        print(f"[bootstrap-credential] {username} password={password}")
        return result["userId"]

    existing = find_user_by_username(session, username)
    if existing is None:
        raise RuntimeError(f"user {username!r} 409'd on create but not found in search")
    print(f"user {username} already exists (id={existing['id']})")
    return existing["id"]


def ensure_grant(session, user_id, project_id, role):
    api_post(
        session,
        f"/users/{user_id}/grants",
        {"projectId": project_id, "roleKeys": [role]},
    )


def get_or_create_action(session):
    action_body = {
        "name": ACTION_NAME,
        "script": ACTION_SOURCE,
        "timeout": "10s",
        "allowedToFail": False,
    }
    result = api_post(session, "/actions", action_body)
    if result is not None:
        return result["id"]
    response = session.post(f"{MGMT}/actions/_search", json={})
    response.raise_for_status()
    for action in response.json().get("result", []):
        if action.get("name") == ACTION_NAME:
            # Unlike every other resource here, an action's own content (its script) is
            # exactly what changes across bootstrap.py edits — a stale action would
            # silently keep running its old script forever otherwise. PUT it back to the
            # current ACTION_SOURCE on every run so a script change actually takes effect
            # against an already-bootstrapped instance, not just a fresh one.
            action_id = action["id"]
            put_response = session.put(f"{MGMT}/actions/{action_id}", json=action_body)
            if put_response.status_code == 400:
                # Same "No Changes" idempotency quirk documented on set_trigger below —
                # PUTting back byte-identical content Zitadel already has returns 400,
                # not a 200 no-op — but each command has its own distinct error ID
                # (confirmed live: UpdateAction's is ACTION-dg4t2, not SetTriggerActions'
                # COMMAND-Nfh52). Treat either as success the same way.
                try:
                    body = put_response.json()
                except ValueError:
                    body = {}
                details = body.get("details") or []
                no_changes = body.get("code") == 9 and any(
                    detail.get("id") in ("COMMAND-Nfh52", "ACTION-dg4t2") for detail in details
                )
                if no_changes:
                    return action_id
            if not put_response.ok:
                print(
                    f"PUT /actions/{action_id} -> {put_response.status_code}: {put_response.text}",
                    file=sys.stderr,
                )
            put_response.raise_for_status()
            return action_id
    raise RuntimeError(f"action {ACTION_NAME!r} 409'd on create but not found in search")


def set_trigger(session, flow_type, trigger_type, action_id):
    # SetTriggerActions is NOT naturally idempotent the way it first appears: calling it
    # again with the exact actionIds it already has returns 400 COMMAND-Nfh52 "No Changes"
    # (confirmed live), not a 200 no-op. Treat that specific response as success, the same
    # way api_post() treats a plain 409 as a no-op — but match precisely on the body's
    # code/id fields so a genuinely different 400 (a real bug) still raises.
    path = f"/flows/{flow_type}/trigger/{trigger_type}"
    response = session.post(
        f"{MGMT}{path}",
        json={"actionIds": [action_id]},
    )
    if response.status_code == 400:
        try:
            body = response.json()
        except ValueError:
            body = {}
        details = body.get("details") or []
        no_changes = body.get("code") == 9 and any(
            detail.get("id") == "COMMAND-Nfh52" for detail in details
        )
        if no_changes:
            return  # trigger already set to this action — idempotent no-op
    if not response.ok:
        # Mirror api_post's diagnostic: Zitadel's gRPC-gateway error bodies name the
        # offending field/condition directly (e.g. COMMAND-xxxx codes) — without this,
        # raise_for_status() below only surfaces the status code, not the reason.
        print(f"POST {path} -> {response.status_code}: {response.text}", file=sys.stderr)
    response.raise_for_status()


def main():
    pat = get_pat_from_secret()
    if pat:
        print(f"using PAT persisted in Secret {PAT_SECRET_NAME!r} (skipping wait_for_pat)")
    else:
        try:
            pat = wait_for_pat()
        except TimeoutError as exc:
            # No Secret yet AND no emptyDir file appeared: either this instance was
            # already bootstrapped before this persistence fix existed and its PAT is
            # unrecoverable, or something upstream is broken. Either way, looping on
            # wait_for_pat() again on the next restart wouldn't help — exit cleanly
            # (the container still parks via `sleep infinity` in the chart's command)
            # rather than raising an unhandled exception into the logs.
            print(f"{exc}; already bootstrapped or PAT never appeared, nothing to do")
            sys.exit(0)
        save_pat_to_secret(pat)
        print(f"persisted PAT to Secret {PAT_SECRET_NAME!r} for future pod restarts")

    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {pat}"
    session.headers["Host"] = ZITADEL_EXTERNAL_DOMAIN

    project_id = get_or_create_project(session)
    print(f"project {PROJECT_NAME!r} id={project_id}")

    for role in ROLES:
        ensure_role(session, project_id, role)
    print(f"roles ensured: {ROLES}")

    for role in ROLES:
        user_id = get_or_create_user(session, role)
        ensure_grant(session, user_id, project_id, role)
        print(f"granted {role} on {PROJECT_NAME!r} to user id={user_id}")

    action_id = get_or_create_action(session)
    print(f"action {ACTION_NAME!r} id={action_id}")

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

    if LOGIN_V2_BASE_URI:
        enable_login_v2_feature(session)
        print(f"Login V2 feature enabled, baseUri={LOGIN_V2_BASE_URI}")
    else:
        print("ZITADEL_LOGIN_V2_BASE_URI unset (zitadel.login.enabled=false) -- skipping Login V2 feature enable")

    instance_id = get_instance_id(session)
    system_api_token = get_system_api_token()
    add_custom_domain(instance_id, "zitadel", system_api_token)
    print("instance domain 'zitadel' added (lets in-cluster callers use the internal Service name)")

    # Complement Token flow (2): Pre Userinfo Creation (4), Pre Access Token Creation (5)
    set_trigger(session, 2, 4, action_id)
    set_trigger(session, 2, 5, action_id)
    print("roles-claim action attached to both Complement Token triggers")

    print("bootstrap complete")


if __name__ == "__main__":
    main()
