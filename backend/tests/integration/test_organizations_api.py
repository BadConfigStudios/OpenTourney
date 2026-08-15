import uuid


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_organizer_claim_creates_organization_and_becomes_owner(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.post(
        "/organizations", json={"name": "Dragon's Den"}, headers=_auth_headers(token)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Dragon's Den"

    list_response = api_client.get("/organizations", headers=_auth_headers(token))
    assert list_response.status_code == 200
    assert [org["id"] for org in list_response.json()] == [body["id"]]


def test_non_organizer_claim_cannot_create_organization(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=[])

    response = api_client.post(
        "/organizations", json={"name": "Dragon's Den"}, headers=_auth_headers(token)
    )

    assert response.status_code == 403


def test_list_organizations_only_shows_orgs_caller_belongs_to(api_client, make_token):
    mine_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    other_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    api_client.post("/organizations", json={"name": "Mine"}, headers=_auth_headers(mine_token))
    api_client.post("/organizations", json={"name": "Other"}, headers=_auth_headers(other_token))

    response = api_client.get("/organizations", headers=_auth_headers(mine_token))

    assert response.status_code == 200
    names = [org["name"] for org in response.json()]
    assert names == ["Mine"]


def _create_org(api_client, token, name="Dragon's Den") -> str:
    return api_client.post(
        "/organizations", json={"name": name}, headers=_auth_headers(token)
    ).json()["id"]


def test_owner_adds_member(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    new_member_uuid = str(uuid.uuid4())

    response = api_client.post(
        f"/organizations/{org_id}/members",
        json={
            "player_uuid": new_member_uuid,
            "source_system": "club-checkin",
            "role": "organizer",
        },
        headers=_auth_headers(owner_token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["player_uuid"] == new_member_uuid
    assert body["role"] == "organizer"


def test_non_owner_cannot_add_member(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.post(
        f"/organizations/{org_id}/members",
        json={
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "role": "organizer",
        },
        headers=_auth_headers(stranger_token),
    )

    assert response.status_code == 403


def test_add_member_to_unknown_organization_returns_404(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.post(
        f"/organizations/{uuid.uuid4()}/members",
        json={
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "role": "organizer",
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 404


def test_add_duplicate_member_returns_409(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    payload = {
        "player_uuid": str(uuid.uuid4()),
        "source_system": "club-checkin",
        "role": "organizer",
    }

    first_response = api_client.post(
        f"/organizations/{org_id}/members",
        json=payload,
        headers=_auth_headers(owner_token),
    )
    assert first_response.status_code == 201

    second_response = api_client.post(
        f"/organizations/{org_id}/members",
        json=payload,
        headers=_auth_headers(owner_token),
    )

    assert second_response.status_code == 409


def test_non_owner_member_cannot_add_member(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)

    organizer_uuid = uuid.uuid4()
    add_organizer_response = api_client.post(
        f"/organizations/{org_id}/members",
        json={
            "player_uuid": str(organizer_uuid),
            "source_system": "club-checkin",
            "role": "organizer",
        },
        headers=_auth_headers(owner_token),
    )
    assert add_organizer_response.status_code == 201

    organizer_token = make_token(player_uuid=organizer_uuid, roles=["organizer"])
    response = api_client.post(
        f"/organizations/{org_id}/members",
        json={
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "role": "organizer",
        },
        headers=_auth_headers(organizer_token),
    )

    assert response.status_code == 403


def test_owner_can_list_members(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    staff_uuid = str(uuid.uuid4())
    api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )

    response = api_client.get(f"/organizations/{org_id}/members", headers=_auth_headers(owner_token))

    assert response.status_code == 200
    roles = {row["role"] for row in response.json()}
    assert roles == {"owner", "organizer"}


def test_non_member_cannot_list_members(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.get(
        f"/organizations/{org_id}/members", headers=_auth_headers(stranger_token)
    )

    assert response.status_code == 403


def test_scorekeeper_cannot_list_members(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    scorekeeper_uuid = str(uuid.uuid4())
    add_response = api_client.post(
        f"/organizations/{org_id}/members",
        json={
            "player_uuid": scorekeeper_uuid,
            "source_system": "club-checkin",
            "role": "scorekeeper",
        },
        headers=_auth_headers(owner_token),
    )
    assert add_response.status_code == 201
    scorekeeper_token = make_token(
        player_uuid=uuid.UUID(scorekeeper_uuid), source_system="club-checkin", roles=["organizer"]
    )

    response = api_client.get(
        f"/organizations/{org_id}/members", headers=_auth_headers(scorekeeper_token)
    )

    assert response.status_code == 403


def test_list_members_404s_for_unknown_org(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.get(f"/organizations/{uuid.uuid4()}/members", headers=_auth_headers(token))

    assert response.status_code == 404


def test_owner_can_revoke_member(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    staff_uuid = str(uuid.uuid4())
    add_response = api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )
    member_id = add_response.json()["id"]

    delete_response = api_client.delete(
        f"/organizations/{org_id}/members/{member_id}", headers=_auth_headers(owner_token)
    )
    list_response = api_client.get(f"/organizations/{org_id}/members", headers=_auth_headers(owner_token))

    assert delete_response.status_code == 204
    assert len(list_response.json()) == 1


def test_non_owner_cannot_revoke_member(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    staff_uuid = str(uuid.uuid4())
    add_response = api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )
    member_id = add_response.json()["id"]
    staff_token = make_token(
        player_uuid=uuid.UUID(staff_uuid), source_system="club-checkin", roles=["organizer"]
    )

    response = api_client.delete(
        f"/organizations/{org_id}/members/{member_id}", headers=_auth_headers(staff_token)
    )

    assert response.status_code == 403


def test_revoke_404s_for_member_not_belonging_to_org(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    other_org_id = _create_org(api_client, owner_token, name="Other Org")
    staff_uuid = str(uuid.uuid4())
    add_response = api_client.post(
        f"/organizations/{other_org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )
    member_id = add_response.json()["id"]

    response = api_client.delete(
        f"/organizations/{org_id}/members/{member_id}", headers=_auth_headers(owner_token)
    )

    assert response.status_code == 404


def test_cannot_revoke_the_only_owner(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    members_response = api_client.get(
        f"/organizations/{org_id}/members", headers=_auth_headers(owner_token)
    )
    owner_member_id = members_response.json()[0]["id"]

    response = api_client.delete(
        f"/organizations/{org_id}/members/{owner_member_id}", headers=_auth_headers(owner_token)
    )

    assert response.status_code == 409

    list_response = api_client.get(
        f"/organizations/{org_id}/members", headers=_auth_headers(owner_token)
    )
    assert len(list_response.json()) == 1


def test_can_revoke_one_of_multiple_owners(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    members_response = api_client.get(
        f"/organizations/{org_id}/members", headers=_auth_headers(owner_token)
    )
    first_owner_member_id = members_response.json()[0]["id"]

    second_owner_uuid = str(uuid.uuid4())
    add_owner_response = api_client.post(
        f"/organizations/{org_id}/members",
        json={
            "player_uuid": second_owner_uuid,
            "source_system": "club-checkin",
            "role": "owner",
        },
        headers=_auth_headers(owner_token),
    )
    assert add_owner_response.status_code == 201
    second_owner_token = make_token(
        player_uuid=uuid.UUID(second_owner_uuid), source_system="club-checkin", roles=["organizer"]
    )

    response = api_client.delete(
        f"/organizations/{org_id}/members/{first_owner_member_id}", headers=_auth_headers(owner_token)
    )

    assert response.status_code == 204

    list_response = api_client.get(
        f"/organizations/{org_id}/members", headers=_auth_headers(second_owner_token)
    )
    remaining = list_response.json()
    assert len(remaining) == 1
    assert remaining[0]["player_uuid"] == second_owner_uuid


def test_revoked_member_loses_event_access(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    staff_uuid = str(uuid.uuid4())
    add_response = api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )
    assert add_response.status_code == 201
    member_id = add_response.json()["id"]
    staff_token = make_token(
        player_uuid=uuid.UUID(staff_uuid), source_system="club-checkin", roles=["organizer"]
    )
    event_response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Staff Event", "organization_id": org_id},
        headers=_auth_headers(staff_token),
    )
    event_id = event_response.json()["id"]

    revoke_response = api_client.delete(
        f"/organizations/{org_id}/members/{member_id}", headers=_auth_headers(owner_token)
    )
    assert revoke_response.status_code == 204
    response = api_client.get(f"/events/{event_id}", headers=_auth_headers(staff_token))

    assert response.status_code == 403


def test_get_organization_returns_name_and_viewer_role(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)

    response = api_client.get(f"/organizations/{org_id}", headers=_auth_headers(owner_token))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == org_id
    assert body["name"] == "Dragon's Den"
    assert body["viewer_role"] == "owner"


def test_get_organization_reflects_non_owner_viewer_role(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    staff_uuid = str(uuid.uuid4())
    api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "scorekeeper"},
        headers=_auth_headers(owner_token),
    )
    staff_token = make_token(
        player_uuid=uuid.UUID(staff_uuid), source_system="club-checkin", roles=["organizer"]
    )

    response = api_client.get(f"/organizations/{org_id}", headers=_auth_headers(staff_token))

    assert response.status_code == 200
    assert response.json()["viewer_role"] == "scorekeeper"


def test_get_organization_404s_for_unknown_org(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.get(f"/organizations/{uuid.uuid4()}", headers=_auth_headers(token))

    assert response.status_code == 404


def test_get_organization_403s_for_non_member(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.get(f"/organizations/{org_id}", headers=_auth_headers(stranger_token))

    assert response.status_code == 403
