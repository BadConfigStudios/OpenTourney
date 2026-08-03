import uuid

from app.models import Entry, Match, Pod, Round
from app.models.rbac import PodRole, PodRoleName


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


def test_deleting_event_cascades_to_pods_entries_rounds_matches_and_roles(
    api_client, make_token, db_session
):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = uuid.UUID(
        api_client.post(
            "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
        ).json()["id"]
    )

    # Pods/Entries/Rounds/Matches/PodRoles have no dedicated endpoints on this branch yet
    # (Task 8+), so insert them directly via the shared db_session — the api_client fixture
    # overrides get_db_session to yield this same session, so the router sees these rows.
    pod = Pod(event_id=event_id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()

    entry = Entry(pod_id=pod.id, player_uuid=uuid.uuid4(), source_system="club-checkin")
    db_session.add(entry)
    db_session.flush()

    round_ = Round(pod_id=pod.id, number=1)
    db_session.add(round_)
    db_session.flush()

    match = Match(round_id=round_.id, entry1_id=entry.id)
    db_session.add(match)

    pod_role = PodRole(
        pod_id=pod.id,
        player_uuid=uuid.uuid4(),
        source_system="club-checkin",
        role=PodRoleName.SCOREKEEPER,
    )
    db_session.add(pod_role)
    db_session.commit()

    pod_id, entry_id, round_id, match_id, pod_role_id = (
        pod.id,
        entry.id,
        round_.id,
        match.id,
        pod_role.id,
    )

    response = api_client.delete(f"/events/{event_id}", headers=_auth_headers(token))

    assert response.status_code == 204
    # Query fresh by id (rather than session.get() on the now-stale local objects) — a
    # bulk delete doesn't evict rows from the session's identity map, so get() on an
    # already-loaded-then-deleted instance raises ObjectDeletedError instead of
    # returning None.
    assert db_session.query(Pod).filter_by(id=pod_id).first() is None
    assert db_session.query(Entry).filter_by(id=entry_id).first() is None
    assert db_session.query(Round).filter_by(id=round_id).first() is None
    assert db_session.query(Match).filter_by(id=match_id).first() is None
    assert db_session.query(PodRole).filter_by(id=pod_role_id).first() is None


def test_event_organizer_of_one_event_cannot_write_to_another_event(api_client, make_token):
    token_a = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    token_b = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    api_client.post("/events", json={"date": "2026-09-01"}, headers=_auth_headers(token_a))
    event_b_id = api_client.post(
        "/events", json={"date": "2026-09-05"}, headers=_auth_headers(token_b)
    ).json()["id"]

    patch_response = api_client.patch(
        f"/events/{event_b_id}", json={"date": "2026-09-06"}, headers=_auth_headers(token_a)
    )
    assert patch_response.status_code == 403

    delete_response = api_client.delete(
        f"/events/{event_b_id}", headers=_auth_headers(token_a)
    )
    assert delete_response.status_code == 403
