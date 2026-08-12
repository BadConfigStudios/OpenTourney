import uuid


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_org(api_client, token, name="Test Org") -> str:
    return api_client.post(
        "/organizations", json={"name": name}, headers=_auth_headers(token)
    ).json()["id"]


def test_organizer_claim_creates_event_and_becomes_its_organizer(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, token)

    response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["date"] == "2026-09-01"
    assert body["name"] == "Friday Standard"
    assert body["organization_id"] == org_id
    assert body["description"] is None

    get_response = api_client.get(f"/events/{body['id']}", headers=_auth_headers(token))
    assert get_response.status_code == 200


def test_event_creation_accepts_optional_description(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, token)

    response = api_client.post(
        "/events",
        json={
            "date": "2026-09-01",
            "name": "Friday Standard",
            "description": "Weekly league night",
            "organization_id": org_id,
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["description"] == "Weekly league night"


def test_non_organizer_claim_cannot_create_event(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=[])

    response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": str(uuid.uuid4())},
        headers=_auth_headers(token),
    )

    assert response.status_code == 403


def test_caller_without_org_membership_cannot_create_event(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(stranger_token),
    )

    assert response.status_code == 403


def test_org_organizer_role_can_create_event(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)

    staff_uuid = str(uuid.uuid4())
    api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )
    staff_token = make_token(
        player_uuid=uuid.UUID(staff_uuid), source_system="club-checkin", roles=["organizer"]
    )

    response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(staff_token),
    )

    assert response.status_code == 201


def test_unrelated_identity_cannot_read_event(api_client, make_token):
    creator_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, creator_token)
    create_response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(creator_token),
    )
    event_id = create_response.json()["id"]

    other_token = make_token(player_uuid=uuid.uuid4(), roles=[])
    response = api_client.get(f"/events/{event_id}", headers=_auth_headers(other_token))

    assert response.status_code == 403


def test_organizer_can_update_and_delete_own_event(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, token)
    event_id = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(token),
    ).json()["id"]

    patch_response = api_client.patch(
        f"/events/{event_id}",
        json={"date": "2026-09-02", "name": "Friday Standard (Moved)"},
        headers=_auth_headers(token),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["date"] == "2026-09-02"
    assert patch_response.json()["name"] == "Friday Standard (Moved)"

    delete_response = api_client.delete(f"/events/{event_id}", headers=_auth_headers(token))
    assert delete_response.status_code == 204

    get_response = api_client.get(f"/events/{event_id}", headers=_auth_headers(token))
    assert get_response.status_code == 404


def test_list_events_only_shows_visible_events(api_client, make_token):
    mine_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    mine_org_id = _create_org(api_client, mine_token, name="Mine Org")
    other_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    other_org_id = _create_org(api_client, other_token, name="Other Org")

    api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Mine", "organization_id": mine_org_id},
        headers=_auth_headers(mine_token),
    )
    api_client.post(
        "/events",
        json={"date": "2026-09-05", "name": "Other", "organization_id": other_org_id},
        headers=_auth_headers(other_token),
    )

    response = api_client.get("/events", headers=_auth_headers(mine_token))

    assert response.status_code == 200
    dates = [event["date"] for event in response.json()]
    assert dates == ["2026-09-01"]
