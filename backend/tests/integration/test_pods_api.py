# backend/tests/integration/test_pods_api.py
import uuid

from app.models import Entry, Match, Pod, Round
from app.models.rbac import PodRole, PodRoleName


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_event(api_client, token) -> str:
    response = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    )
    return response.json()["id"]


def test_organizer_creates_pod_for_own_event(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = _create_event(api_client, token)

    response = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["event_id"] == event_id


def test_second_pod_for_same_event_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = _create_event(api_client, token)
    api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    )

    response = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 409


def test_non_organizer_cannot_create_pod(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = _create_event(api_client, owner_token)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(stranger_token),
    )

    assert response.status_code == 403


def test_organizer_can_update_and_delete_pod(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = _create_event(api_client, token)
    pod_id = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    ).json()["id"]

    patch_response = api_client.patch(
        f"/pods/{pod_id}",
        json={"format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    )
    assert patch_response.status_code == 200

    delete_response = api_client.delete(f"/pods/{pod_id}", headers=_auth_headers(token))
    assert delete_response.status_code == 204

    get_response = api_client.get(f"/pods/{pod_id}", headers=_auth_headers(token))
    assert get_response.status_code == 404


def test_list_pods_requires_event_visibility(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = _create_event(api_client, owner_token)
    api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(owner_token),
    )

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=[])
    response = api_client.get(
        "/pods", params={"event_id": event_id}, headers=_auth_headers(stranger_token)
    )

    assert response.status_code == 403


def test_deleting_pod_cascades_to_rounds_matches_entries_and_roles(
    api_client, make_token, db_session
):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = _create_event(api_client, token)
    pod_id = uuid.UUID(
        api_client.post(
            "/pods",
            json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
            headers=_auth_headers(token),
        ).json()["id"]
    )

    # Entries/pod-role endpoints don't exist on this branch yet (Task 9+), so insert them
    # directly via the shared db_session — the api_client fixture overrides get_db_session
    # to yield this same session, so the router sees these rows.
    entry = Entry(pod_id=pod_id, player_uuid=uuid.uuid4(), source_system="club-checkin")
    db_session.add(entry)
    db_session.flush()

    round_ = Round(pod_id=pod_id, number=1)
    db_session.add(round_)
    db_session.flush()

    match = Match(round_id=round_.id, entry1_id=entry.id)
    db_session.add(match)

    pod_role = PodRole(
        pod_id=pod_id,
        player_uuid=uuid.uuid4(),
        source_system="club-checkin",
        role=PodRoleName.SCOREKEEPER,
    )
    db_session.add(pod_role)
    db_session.commit()

    entry_id, round_id, match_id, pod_role_id = entry.id, round_.id, match.id, pod_role.id

    response = api_client.delete(f"/pods/{pod_id}", headers=_auth_headers(token))

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


def test_pod_organizer_of_one_event_cannot_write_to_another_events_pod(api_client, make_token):
    token_a = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    token_b = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    event_a_id = _create_event(api_client, token_a)
    api_client.post(
        "/pods",
        json={"event_id": event_a_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token_a),
    )

    event_b_id = _create_event(api_client, token_b)
    pod_b_id = api_client.post(
        "/pods",
        json={"event_id": event_b_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token_b),
    ).json()["id"]

    patch_response = api_client.patch(
        f"/pods/{pod_b_id}",
        json={"format_slug": "single-elim", "game_slug": "generic"},
        headers=_auth_headers(token_a),
    )
    assert patch_response.status_code == 403

    delete_response = api_client.delete(f"/pods/{pod_b_id}", headers=_auth_headers(token_a))
    assert delete_response.status_code == 403


def test_pod_organizer_of_one_event_cannot_read_another_events_pod(api_client, make_token):
    token_a = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    token_b = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    event_a_id = _create_event(api_client, token_a)
    api_client.post(
        "/pods",
        json={"event_id": event_a_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token_a),
    )

    event_b_id = _create_event(api_client, token_b)
    pod_b_id = api_client.post(
        "/pods",
        json={"event_id": event_b_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token_b),
    ).json()["id"]

    get_response = api_client.get(f"/pods/{pod_b_id}", headers=_auth_headers(token_a))
    assert get_response.status_code == 403
