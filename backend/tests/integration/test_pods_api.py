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


def _create_pod(api_client, token) -> str:
    event_id = _create_event(api_client, token)
    return api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    ).json()["id"]


def _add_entry(api_client, token, pod_id) -> str:
    return api_client.post(
        "/entries",
        json={
            "pod_id": pod_id,
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "metadata": {},
        },
        headers=_auth_headers(token),
    ).json()["id"]


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
    assert patch_response.json()["game_slug"] == "generic"

    # Re-GET to confirm the update actually persisted, not just that the PATCH
    # response body claimed it did.
    confirm_response = api_client.get(f"/pods/{pod_id}", headers=_auth_headers(token))
    assert confirm_response.status_code == 200
    assert confirm_response.json()["game_slug"] == "generic"

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


def test_list_pods_filters_to_requested_event_only(api_client, make_token):
    token_a = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    token_b = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    event_a_id = _create_event(api_client, token_a)
    pod_a_id = api_client.post(
        "/pods",
        json={"event_id": event_a_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token_a),
    ).json()["id"]

    event_b_id = _create_event(api_client, token_b)
    api_client.post(
        "/pods",
        json={"event_id": event_b_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token_b),
    )

    response = api_client.get(
        "/pods", params={"event_id": event_a_id}, headers=_auth_headers(token_a)
    )

    assert response.status_code == 200
    pods = response.json()
    assert len(pods) == 1
    assert pods[0]["id"] == pod_a_id
    assert pods[0]["event_id"] == event_a_id


def test_get_pod_by_id_returns_matching_pod(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = _create_event(api_client, token)
    created = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    ).json()

    response = api_client.get(f"/pods/{created['id']}", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["event_id"] == event_id
    assert body["format_slug"] == "swiss"
    assert body["game_slug"] == "generic"


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


def test_create_pod_with_unknown_game_slug_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = _create_event(api_client, token)

    response = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "pokemon-tcg"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_update_pod_with_unknown_game_slug_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = _create_event(api_client, token)
    pod_id = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    ).json()["id"]

    response = api_client.patch(
        f"/pods/{pod_id}",
        json={"format_slug": "swiss", "game_slug": "pokemon-tcg"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_organizer_completes_pod_with_no_rounds(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)

    response = api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))

    assert response.status_code == 200
    assert response.json()["completed_at"] is not None


def test_completing_already_complete_pod_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))

    response = api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))

    assert response.status_code == 409


def test_completing_pod_with_unreported_match_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    _add_entry(api_client, token, pod_id)
    api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    response = api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))

    assert response.status_code == 409


def test_non_organizer_cannot_complete_pod(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(stranger_token))

    assert response.status_code == 403


def test_updating_pod_after_completion_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))

    response = api_client.patch(
        f"/pods/{pod_id}",
        json={"format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 409


def test_report_is_empty_for_pod_with_no_entries(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)

    response = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "is_complete": False,
        "rounds_played": 0,
        "is_partial": False,
        "active_entry_count": 0,
        "recommended_rounds": 0,
        "standings": [],
    }


def test_report_reflects_reported_results(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    _add_entry(api_client, token, pod_id)
    round_ = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    match_id = round_["matches"][0]["id"]
    api_client.post(
        f"/matches/{match_id}/result", json={"result": "entry1_win"}, headers=_auth_headers(token)
    )

    response = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["is_partial"] is False
    assert body["rounds_played"] == 1
    assert body["standings"][0]["points"] == 3
    assert body["standings"][0]["rank"] == 1


def test_report_is_partial_when_current_round_has_unreported_matches(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    _add_entry(api_client, token, pod_id)
    api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    response = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["is_partial"] is True
    assert body["rounds_played"] == 1
    # Round 1 itself is excluded from standings (it's the in-progress round being
    # partial-filtered out) — both entries still appear, at 0 points each, not an
    # empty list: compute_standings still runs over the (empty) usable_rounds and
    # all entries, it just has no completed-round results to award points from.
    assert len(body["standings"]) == 2
    assert {row["points"] for row in body["standings"]} == {0}


def test_report_includes_active_entry_count_and_recommended_rounds(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    entry_ids = [_add_entry(api_client, token, pod_id) for _ in range(4)]

    response = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token))
    body = response.json()
    assert body["active_entry_count"] == 4
    assert body["recommended_rounds"] == 2

    api_client.post(f"/entries/{entry_ids[0]}/drop", headers=_auth_headers(token))

    response = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token))
    body = response.json()
    assert body["active_entry_count"] == 3
    assert body["recommended_rounds"] == 2


def test_stranger_without_pod_access_cannot_view_report(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)

    # A stranger who is neither the pod's event organizer nor holds a PodRole on
    # this pod fails require_pod_access's `pod_access_allowed` check, regardless of
    # whether they hold an organizer claim elsewhere/for a different event.
    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(stranger_token))

    assert response.status_code == 403


def test_report_for_unknown_pod_is_not_found(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.get(f"/pods/{uuid.uuid4()}/report", headers=_auth_headers(token))

    assert response.status_code == 404


def test_report_for_unrecognized_format_slug_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = _create_event(api_client, token)
    pod_id = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "single-elim", "game_slug": "generic"},
        headers=_auth_headers(token),
    ).json()["id"]

    response = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token))

    assert response.status_code == 422


def test_report_marks_is_complete_after_pod_completion(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))

    response = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token))

    assert response.json()["is_complete"] is True
