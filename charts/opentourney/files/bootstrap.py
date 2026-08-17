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
    `roles` claim, and attaches it to both Complement Token triggers

Idempotent: every create call treats a 409 ("already exists") response as a
no-op success, then resolves the existing resource's ID via a _search call
so re-running this script (e.g. on every Pod restart / helm upgrade) is safe.
"""
import os
import secrets
import string
import sys
import time

import requests

ZITADEL_BASE = "http://localhost:8080"
MGMT = f"{ZITADEL_BASE}/management/v1"
# Zitadel validates the Host header against ZITADEL_EXTERNALDOMAIN (anti-DNS-rebinding
# protection) and returns 404 for any request presenting a different Host — including
# the "localhost:8080" the requests library would otherwise send by default when hitting
# this same-pod address. Every request must carry the external domain as its Host header.
ZITADEL_EXTERNAL_DOMAIN = os.environ["ZITADEL_EXTERNAL_DOMAIN"]
PAT_PATH = "/pat/pat.txt"
ROLES = ["organizer", "scorekeeper", "player"]
PROJECT_NAME = "OpenTourney"
ACTION_NAME = "addRolesClaim"

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
    result = api_post(
        session,
        "/actions",
        {
            "name": ACTION_NAME,
            "script": ACTION_SOURCE,
            "timeout": "10s",
            "allowedToFail": False,
        },
    )
    if result is not None:
        return result["id"]
    response = session.post(f"{MGMT}/actions/_search", json={})
    response.raise_for_status()
    for action in response.json().get("result", []):
        if action.get("name") == ACTION_NAME:
            return action["id"]
    raise RuntimeError(f"action {ACTION_NAME!r} 409'd on create but not found in search")


def set_trigger(session, flow_type, trigger_type, action_id):
    # Replace, not append — naturally idempotent, no 409 handling needed.
    path = f"/flows/{flow_type}/trigger/{trigger_type}"
    response = session.post(
        f"{MGMT}{path}",
        json={"actionIds": [action_id]},
    )
    if not response.ok:
        # Mirror api_post's diagnostic: Zitadel's gRPC-gateway error bodies name the
        # offending field/condition directly (e.g. COMMAND-xxxx codes) — without this,
        # raise_for_status() below only surfaces the status code, not the reason.
        print(f"POST {path} -> {response.status_code}: {response.text}", file=sys.stderr)
    response.raise_for_status()


def main():
    pat = wait_for_pat()
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

    # Complement Token flow (2): Pre Userinfo Creation (4), Pre Access Token Creation (5)
    set_trigger(session, 2, 4, action_id)
    set_trigger(session, 2, 5, action_id)
    print("roles-claim action attached to both Complement Token triggers")

    print("bootstrap complete")


if __name__ == "__main__":
    main()
