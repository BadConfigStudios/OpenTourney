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


def test_report_screen_flow_partial_then_complete(api_client, make_token):
    """Mirrors the Phase 7 PR4 Report screen's sequence of API calls:
    view a partial report mid-round, finish reporting, complete the pod,
    and confirm the final report reflects completion.
    """
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    for _ in range(2):
        _add_entry(api_client, token, pod_id)

    round1 = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    match_id = round1["matches"][0]["id"]

    partial_report = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token)).json()
    assert partial_report["is_complete"] is False
    assert partial_report["is_partial"] is True
    assert partial_report["rounds_played"] == 1

    complete_attempt = api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))
    assert complete_attempt.status_code == 409

    api_client.post(
        f"/matches/{match_id}/result",
        json={"result": "entry1_win", "method": "manual_entry"},
        headers=_auth_headers(token),
    )

    reported_report = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token)).json()
    assert reported_report["is_partial"] is False
    assert reported_report["is_complete"] is False
    assert [row["rank"] for row in reported_report["standings"]] == [1, 2]

    complete_response = api_client.post(f"/pods/{pod_id}/complete", headers=_auth_headers(token))
    assert complete_response.status_code == 200

    final_report = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token)).json()
    assert final_report["is_complete"] is True
    assert final_report["is_partial"] is False
