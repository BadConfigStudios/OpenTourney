# backend/tests/integration/test_events_api.py
import uuid


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_organizer_claim_creates_event_and_becomes_its_organizer(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["date"] == "2026-09-01"

    get_response = api_client.get(f"/events/{body['id']}", headers=_auth_headers(token))
    assert get_response.status_code == 200


def test_non_organizer_claim_cannot_create_event(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=[])

    response = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    )

    assert response.status_code == 403


def test_unrelated_identity_cannot_read_event(api_client, make_token):
    creator_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    create_response = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(creator_token)
    )
    event_id = create_response.json()["id"]

    other_token = make_token(player_uuid=uuid.uuid4(), roles=[])
    response = api_client.get(f"/events/{event_id}", headers=_auth_headers(other_token))

    assert response.status_code == 403


def test_organizer_can_update_and_delete_own_event(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    ).json()["id"]

    patch_response = api_client.patch(
        f"/events/{event_id}", json={"date": "2026-09-02"}, headers=_auth_headers(token)
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["date"] == "2026-09-02"

    delete_response = api_client.delete(f"/events/{event_id}", headers=_auth_headers(token))
    assert delete_response.status_code == 204

    get_response = api_client.get(f"/events/{event_id}", headers=_auth_headers(token))
    assert get_response.status_code == 404


def test_list_events_only_shows_visible_events(api_client, make_token):
    mine_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    other_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    api_client.post("/events", json={"date": "2026-09-01"}, headers=_auth_headers(mine_token))
    api_client.post("/events", json={"date": "2026-09-05"}, headers=_auth_headers(other_token))

    response = api_client.get("/events", headers=_auth_headers(mine_token))

    assert response.status_code == 200
    dates = [event["date"] for event in response.json()]
    assert dates == ["2026-09-01"]
