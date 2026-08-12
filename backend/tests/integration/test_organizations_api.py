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
