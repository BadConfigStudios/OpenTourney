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


def _pod_with_one_match(api_client, token):
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    _add_entry(api_client, token, pod_id)
    round_ = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    return pod_id, round_["matches"][0]["id"]


def test_organizer_reports_match_result(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    _, match_id = _pod_with_one_match(api_client, token)

    response = api_client.post(
        f"/matches/{match_id}/result", json={"result": "entry1_win"}, headers=_auth_headers(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "entry1_win"
    assert body["reported_by"] == body["witnessed_by"]
    assert body["reported_by"] is not None


def test_scorekeeper_can_report_match_result(api_client, make_token):
    organizer_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id, match_id = _pod_with_one_match(api_client, organizer_token)
    scorekeeper_uuid = uuid.uuid4()
    api_client.post(
        f"/pods/{pod_id}/roles",
        json={
            "player_uuid": str(scorekeeper_uuid),
            "source_system": "club-checkin",
            "role": "scorekeeper",
        },
        headers=_auth_headers(organizer_token),
    )
    scorekeeper_token = make_token(player_uuid=scorekeeper_uuid, source_system="club-checkin")

    response = api_client.post(
        f"/matches/{match_id}/result",
        json={"result": "tie"},
        headers=_auth_headers(scorekeeper_token),
    )

    assert response.status_code == 200


def test_plain_user_role_cannot_report_match_result(api_client, make_token):
    organizer_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id, match_id = _pod_with_one_match(api_client, organizer_token)
    player_uuid = uuid.uuid4()
    api_client.post(
        f"/pods/{pod_id}/roles",
        json={
            "player_uuid": str(player_uuid),
            "source_system": "club-checkin",
            "role": "user",
        },
        headers=_auth_headers(organizer_token),
    )
    player_token = make_token(player_uuid=player_uuid, source_system="club-checkin")

    response = api_client.post(
        f"/matches/{match_id}/result",
        json={"result": "entry1_win"},
        headers=_auth_headers(player_token),
    )

    assert response.status_code == 403


def test_reporting_unreported_as_result_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    _, match_id = _pod_with_one_match(api_client, token)

    response = api_client.post(
        f"/matches/{match_id}/result",
        json={"result": "unreported"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_reporting_a_bye_match_result_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    round_ = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    bye_match_id = round_["matches"][0]["id"]

    response = api_client.post(
        f"/matches/{bye_match_id}/result",
        json={"result": "entry1_win"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 409


def test_reporting_result_for_unknown_match_is_not_found(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.post(
        f"/matches/{uuid.uuid4()}/result",
        json={"result": "entry1_win"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 404
