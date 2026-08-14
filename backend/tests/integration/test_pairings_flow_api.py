import uuid


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_pod(api_client, token) -> str:
    org_id = api_client.post(
        "/organizations", json={"name": "Test Org"}, headers=_auth_headers(token)
    ).json()["id"]
    event_id = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Test Event", "organization_id": org_id},
        headers=_auth_headers(token),
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


def test_pairings_screen_flow_generate_report_generate_next_round(api_client, make_token):
    """Mirrors the Phase 7 PR3 Pairings screen's sequence of API calls:
    generate round one, report both matches, generate round two, and
    confirm round history accumulates with the reported results intact.
    """
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    for _ in range(4):
        _add_entry(api_client, token, pod_id)

    round1 = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    assert round1["number"] == 1
    assert len(round1["matches"]) == 2

    for match in round1["matches"]:
        response = api_client.post(
            f"/matches/{match['id']}/result",
            json={"result": "entry1_win", "method": "manual_entry"},
            headers=_auth_headers(token),
        )
        assert response.status_code == 200
        assert response.json()["method"] == "manual_entry"

    round2 = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    assert round2["number"] == 2

    rounds = api_client.get(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    assert [r["number"] for r in rounds] == [1, 2]
    assert all(m["result"] == "entry1_win" for m in rounds[0]["matches"])
    assert all(m["result"] == "unreported" for m in rounds[1]["matches"])
