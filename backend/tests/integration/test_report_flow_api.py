import uuid

import pytest


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


def test_report_ranks_by_omw_when_match_points_tie(api_client, make_token):
    """A real tiebreak scenario (not a coincidental UUID tie): two entries
    finish with equal match points but faced different-strength opponents,
    so OMW% -- not entry-id string comparison -- must decide rank order."""
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    for _ in range(4):
        _add_entry(api_client, token, pod_id)

    def _report(match_id: str, winner_id: str, entry1_id: str) -> None:
        result = "entry1_win" if winner_id == entry1_id else "entry2_win"
        response = api_client.post(
            f"/matches/{match_id}/result",
            json={"result": result, "method": "manual_entry"},
            headers=_auth_headers(token),
        )
        assert response.status_code == 200

    round1 = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    match1, match2 = round1["matches"]
    w1, l1 = match1["entry1_id"], match1["entry2_id"]
    w2, l2 = match2["entry1_id"], match2["entry2_id"]
    _report(match1["id"], winner_id=w1, entry1_id=match1["entry1_id"])
    _report(match2["id"], winner_id=w2, entry1_id=match2["entry1_id"])

    round2 = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token)).json()
    winners_match = next(
        m for m in round2["matches"] if {m["entry1_id"], m["entry2_id"]} == {w1, w2}
    )
    losers_match = next(
        m for m in round2["matches"] if {m["entry1_id"], m["entry2_id"]} == {l1, l2}
    )
    # w2 takes the winners' match (climbing to 2-0); w1 falls to 1-1.
    _report(winners_match["id"], winner_id=w2, entry1_id=winners_match["entry1_id"])
    # l1 takes the losers' match (climbing to 1-1); l2 stays 0-2.
    _report(losers_match["id"], winner_id=l1, entry1_id=losers_match["entry1_id"])

    report = api_client.get(f"/pods/{pod_id}/report", headers=_auth_headers(token)).json()
    standings = {row["entry_id"]: row for row in report["standings"]}

    # w1 and l1 both sit at 3 points (1 win, 1 loss), but w1's loss was to
    # w2 (a 6-point, 2-0 opponent) while l1's loss was to w1 (a 3-point
    # opponent) -- w1 faced the stronger average opponent, so OMW% must
    # rank it above l1 despite the equal points.
    assert standings[w1]["points"] == standings[l1]["points"] == 3
    assert len(standings[w1]["tiebreakers"]) == 2
    assert standings[w1]["tiebreakers"][0] == pytest.approx(0.75)
    assert standings[l1]["tiebreakers"][0] == pytest.approx(0.415)
    assert standings[w1]["rank"] < standings[l1]["rank"]
