import uuid

from app.models import Match, MatchResult, Round


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_pod(api_client, token, format_slug="swiss") -> str:
    event_id = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    ).json()["id"]
    return api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": format_slug, "game_slug": "generic"},
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


def test_organizer_generates_round_one(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    _add_entry(api_client, token, pod_id)

    response = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    assert response.status_code == 201
    body = response.json()
    assert body["number"] == 1
    assert len(body["matches"]) == 1
    assert body["matches"][0]["entry2_id"] is not None


def test_non_organizer_cannot_generate_round(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)
    _add_entry(api_client, owner_token, pod_id)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(stranger_token))

    assert response.status_code == 403


def test_round_generation_rejects_empty_pod(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)

    response = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    assert response.status_code == 409


def test_round_generation_rejects_unrecognized_format_slug(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token, format_slug="single-elim")
    _add_entry(api_client, token, pod_id)

    response = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    assert response.status_code == 422


def test_round_generation_blocked_until_prior_round_fully_reported(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    _add_entry(api_client, token, pod_id)
    api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    response = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    assert response.status_code == 409


def test_duplicate_round_number_returns_409(api_client, make_token, db_session):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    _add_entry(api_client, token, pod_id)

    round_one = api_client.post(
        f"/pods/{pod_id}/rounds", headers=_auth_headers(token)
    ).json()
    round_one_id = uuid.UUID(round_one["id"])

    # Mark round 1's match reported so the format allows generating another round.
    match = db_session.query(Match).filter_by(round_id=round_one_id).one()
    match.result = MatchResult.ENTRY1_WIN
    db_session.commit()

    # Simulate a lost race: another writer already committed round number 3,
    # leaving a gap (numbers 1 and 3 exist, not 2). The route computes the next
    # round number as len(previous_rounds) + 1 rather than max(number) + 1, so
    # with previous_rounds == [round 1, round 3] it computes len(...) + 1 == 3,
    # colliding with the round already sitting at number 3.
    db_session.add(Round(pod_id=uuid.UUID(pod_id), number=3))
    db_session.commit()

    response = api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    assert response.status_code == 409


def test_organizer_can_list_rounds_with_nested_matches(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    _add_entry(api_client, token, pod_id)
    _add_entry(api_client, token, pod_id)
    api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    response = api_client.get(f"/pods/{pod_id}/rounds", headers=_auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert len(body[0]["matches"]) == 1


def test_pod_role_without_organizer_claim_can_list_rounds(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)
    _add_entry(api_client, owner_token, pod_id)
    _add_entry(api_client, owner_token, pod_id)
    api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(owner_token))

    scorekeeper_uuid = uuid.uuid4()
    api_client.post(
        f"/pods/{pod_id}/roles",
        json={
            "player_uuid": str(scorekeeper_uuid),
            "source_system": "club-checkin",
            "role": "scorekeeper",
        },
        headers=_auth_headers(owner_token),
    )
    scorekeeper_token = make_token(player_uuid=scorekeeper_uuid, roles=[])

    response = api_client.get(
        f"/pods/{pod_id}/rounds", headers=_auth_headers(scorekeeper_token)
    )

    assert response.status_code == 200


def test_stranger_without_pod_role_or_organizer_claim_cannot_list_rounds(
    api_client, make_token
):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)
    _add_entry(api_client, owner_token, pod_id)
    _add_entry(api_client, owner_token, pod_id)
    api_client.post(f"/pods/{pod_id}/rounds", headers=_auth_headers(owner_token))

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=[])

    response = api_client.get(f"/pods/{pod_id}/rounds", headers=_auth_headers(stranger_token))

    assert response.status_code == 403
