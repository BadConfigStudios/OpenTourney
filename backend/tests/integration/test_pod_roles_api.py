import uuid


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_pod(api_client, token) -> str:
    event_id = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    ).json()["id"]
    return api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    ).json()["id"]


def test_organizer_assigns_scorekeeper_role(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    scorekeeper_uuid = str(uuid.uuid4())

    response = api_client.post(
        f"/pods/{pod_id}/roles",
        json={
            "player_uuid": scorekeeper_uuid,
            "source_system": "club-checkin",
            "role": "scorekeeper",
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["role"] == "scorekeeper"


def test_organizer_of_other_event_cannot_assign_roles(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.post(
        f"/pods/{pod_id}/roles",
        json={
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "role": "user",
        },
        headers=_auth_headers(stranger_token),
    )

    assert response.status_code == 403


def test_duplicate_role_assignment_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    identity_uuid = str(uuid.uuid4())
    api_client.post(
        f"/pods/{pod_id}/roles",
        json={"player_uuid": identity_uuid, "source_system": "club-checkin", "role": "user"},
        headers=_auth_headers(token),
    )

    response = api_client.post(
        f"/pods/{pod_id}/roles",
        json={
            "player_uuid": identity_uuid,
            "source_system": "club-checkin",
            "role": "scorekeeper",
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 409


def test_organizer_can_list_and_revoke_role(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    role_id = api_client.post(
        f"/pods/{pod_id}/roles",
        json={
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "role": "user",
        },
        headers=_auth_headers(token),
    ).json()["id"]

    list_response = api_client.get(f"/pods/{pod_id}/roles", headers=_auth_headers(token))
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    delete_response = api_client.delete(
        f"/pods/{pod_id}/roles/{role_id}", headers=_auth_headers(token)
    )
    assert delete_response.status_code == 204

    list_after_response = api_client.get(f"/pods/{pod_id}/roles", headers=_auth_headers(token))
    assert list_after_response.json() == []


def test_organizer_of_other_event_cannot_list_roles(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)
    api_client.post(
        f"/pods/{pod_id}/roles",
        json={
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "role": "user",
        },
        headers=_auth_headers(owner_token),
    )

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.get(f"/pods/{pod_id}/roles", headers=_auth_headers(stranger_token))

    assert response.status_code == 403


def test_organizer_of_other_event_cannot_revoke_role(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)
    role_id = api_client.post(
        f"/pods/{pod_id}/roles",
        json={
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "role": "user",
        },
        headers=_auth_headers(owner_token),
    ).json()["id"]

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.delete(
        f"/pods/{pod_id}/roles/{role_id}", headers=_auth_headers(stranger_token)
    )

    assert response.status_code == 403
