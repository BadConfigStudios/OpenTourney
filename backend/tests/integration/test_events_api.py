import uuid

from app.models import Entry, Match, Pod, Round
from app.models.rbac import PodRole, PodRoleName


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_org(api_client, token, name="Test Org") -> str:
    return api_client.post(
        "/organizations", json={"name": name}, headers=_auth_headers(token)
    ).json()["id"]


def test_organizer_claim_creates_event_and_becomes_its_organizer(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, token)

    response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["date"] == "2026-09-01"
    assert body["name"] == "Friday Standard"
    assert body["organization_id"] == org_id
    assert body["description"] is None

    get_response = api_client.get(f"/events/{body['id']}", headers=_auth_headers(token))
    assert get_response.status_code == 200


def test_event_creation_accepts_optional_description(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, token)

    response = api_client.post(
        "/events",
        json={
            "date": "2026-09-01",
            "name": "Friday Standard",
            "description": "Weekly league night",
            "organization_id": org_id,
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["description"] == "Weekly league night"


def test_non_organizer_claim_cannot_create_event(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=[])

    response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": str(uuid.uuid4())},
        headers=_auth_headers(token),
    )

    assert response.status_code == 403


def test_caller_without_org_membership_cannot_create_event(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(stranger_token),
    )

    assert response.status_code == 403


def test_org_organizer_role_can_create_event(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)

    staff_uuid = str(uuid.uuid4())
    api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )
    staff_token = make_token(
        player_uuid=uuid.UUID(staff_uuid), source_system="club-checkin", roles=["organizer"]
    )

    response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(staff_token),
    )

    assert response.status_code == 201


def test_org_scorekeeper_role_cannot_create_event(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)

    staff_uuid = str(uuid.uuid4())
    api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "scorekeeper"},
        headers=_auth_headers(owner_token),
    )
    staff_token = make_token(
        player_uuid=uuid.UUID(staff_uuid), source_system="club-checkin", roles=["organizer"]
    )

    response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(staff_token),
    )

    assert response.status_code == 403


def test_org_judge_role_cannot_create_event(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)

    staff_uuid = str(uuid.uuid4())
    api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "judge"},
        headers=_auth_headers(owner_token),
    )
    staff_token = make_token(
        player_uuid=uuid.UUID(staff_uuid), source_system="club-checkin", roles=["organizer"]
    )

    response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(staff_token),
    )

    assert response.status_code == 403


def test_unrelated_identity_cannot_read_event(api_client, make_token):
    creator_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, creator_token)
    create_response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(creator_token),
    )
    event_id = create_response.json()["id"]

    other_token = make_token(player_uuid=uuid.uuid4(), roles=[])
    response = api_client.get(f"/events/{event_id}", headers=_auth_headers(other_token))

    assert response.status_code == 403


def test_organizer_can_update_and_delete_own_event(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, token)
    event_id = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(token),
    ).json()["id"]

    patch_response = api_client.patch(
        f"/events/{event_id}",
        json={"date": "2026-09-02", "name": "Friday Standard (Moved)"},
        headers=_auth_headers(token),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["date"] == "2026-09-02"
    assert patch_response.json()["name"] == "Friday Standard (Moved)"

    delete_response = api_client.delete(f"/events/{event_id}", headers=_auth_headers(token))
    assert delete_response.status_code == 204

    get_response = api_client.get(f"/events/{event_id}", headers=_auth_headers(token))
    assert get_response.status_code == 404


def test_patch_omitting_description_preserves_existing_description(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, token)
    event_id = api_client.post(
        "/events",
        json={
            "date": "2026-09-01",
            "name": "Friday Standard",
            "description": "Weekly league night",
            "organization_id": org_id,
        },
        headers=_auth_headers(token),
    ).json()["id"]

    patch_response = api_client.patch(
        f"/events/{event_id}",
        json={"date": "2026-09-02"},
        headers=_auth_headers(token),
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["date"] == "2026-09-02"
    assert patch_response.json()["name"] == "Friday Standard"
    assert patch_response.json()["description"] == "Weekly league night"


def test_patch_rejects_explicit_null_date(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, token)
    event_id = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(token),
    ).json()["id"]

    patch_response = api_client.patch(
        f"/events/{event_id}",
        json={"date": None},
        headers=_auth_headers(token),
    )

    assert patch_response.status_code == 422


def test_patch_rejects_explicit_null_name(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, token)
    event_id = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
        headers=_auth_headers(token),
    ).json()["id"]

    patch_response = api_client.patch(
        f"/events/{event_id}",
        json={"name": None},
        headers=_auth_headers(token),
    )

    assert patch_response.status_code == 422


def test_list_events_only_shows_visible_events(api_client, make_token):
    mine_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    mine_org_id = _create_org(api_client, mine_token, name="Mine Org")
    other_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    other_org_id = _create_org(api_client, other_token, name="Other Org")

    api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Mine", "organization_id": mine_org_id},
        headers=_auth_headers(mine_token),
    )
    api_client.post(
        "/events",
        json={"date": "2026-09-05", "name": "Other", "organization_id": other_org_id},
        headers=_auth_headers(other_token),
    )

    response = api_client.get("/events", headers=_auth_headers(mine_token))

    assert response.status_code == 200
    dates = [event["date"] for event in response.json()]
    assert dates == ["2026-09-01"]


def test_deleting_event_cascades_to_pods_entries_rounds_matches_and_roles(
    api_client, make_token, db_session
):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, token)
    event_id = uuid.UUID(
        api_client.post(
            "/events",
            json={"date": "2026-09-01", "name": "Friday Standard", "organization_id": org_id},
            headers=_auth_headers(token),
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

    delete_response = api_client.delete(f"/events/{event_id}", headers=_auth_headers(token))
    assert delete_response.status_code == 204

    # Safe because SQLAlchemy 2.0's synchronize_session="auto" evicts bulk-deleted rows from
    # the identity map; a DB-level cascade would break this.
    assert db_session.get(Pod, pod_id) is None
    assert db_session.get(Entry, entry_id) is None
    assert db_session.get(Round, round_id) is None
    assert db_session.get(Match, match_id) is None
    assert db_session.get(PodRole, pod_role_id) is None


def test_event_organizer_of_one_event_cannot_write_to_another_event(api_client, make_token):
    token_a = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_a_id = _create_org(api_client, token_a, name="Org A")
    token_b = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_b_id = _create_org(api_client, token_b, name="Org B")

    api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Event A", "organization_id": org_a_id},
        headers=_auth_headers(token_a),
    )
    event_b_id = api_client.post(
        "/events",
        json={"date": "2026-09-05", "name": "Event B", "organization_id": org_b_id},
        headers=_auth_headers(token_b),
    ).json()["id"]

    patch_response = api_client.patch(
        f"/events/{event_b_id}",
        json={"date": "2026-09-06", "name": "Event B (Moved)"},
        headers=_auth_headers(token_a),
    )
    assert patch_response.status_code == 403

    delete_response = api_client.delete(
        f"/events/{event_b_id}", headers=_auth_headers(token_a)
    )
    assert delete_response.status_code == 403


def test_org_owner_can_operate_on_event_created_by_org_organizer(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)

    staff_uuid = str(uuid.uuid4())
    add_member_response = api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )
    assert add_member_response.status_code == 201
    staff_token = make_token(
        player_uuid=uuid.UUID(staff_uuid), source_system="club-checkin", roles=["organizer"]
    )
    create_response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Staff-Created Event", "organization_id": org_id},
        headers=_auth_headers(staff_token),
    )
    event_id = create_response.json()["id"]

    get_response = api_client.get(f"/events/{event_id}", headers=_auth_headers(owner_token))
    patch_response = api_client.patch(
        f"/events/{event_id}", json={"name": "Renamed by Owner"}, headers=_auth_headers(owner_token)
    )

    assert get_response.status_code == 200
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Renamed by Owner"

    delete_response = api_client.delete(f"/events/{event_id}", headers=_auth_headers(owner_token))
    assert delete_response.status_code == 204


def test_org_organizer_can_operate_on_event_created_by_org_owner(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    org_id = _create_org(api_client, owner_token)
    create_response = api_client.post(
        "/events",
        json={"date": "2026-09-01", "name": "Owner-Created Event", "organization_id": org_id},
        headers=_auth_headers(owner_token),
    )
    event_id = create_response.json()["id"]

    staff_uuid = str(uuid.uuid4())
    add_member_response = api_client.post(
        f"/organizations/{org_id}/members",
        json={"player_uuid": staff_uuid, "source_system": "club-checkin", "role": "organizer"},
        headers=_auth_headers(owner_token),
    )
    assert add_member_response.status_code == 201
    staff_token = make_token(
        player_uuid=uuid.UUID(staff_uuid), source_system="club-checkin", roles=["organizer"]
    )

    get_response = api_client.get(f"/events/{event_id}", headers=_auth_headers(staff_token))
    patch_response = api_client.patch(
        f"/events/{event_id}", json={"name": "Renamed by Organizer"}, headers=_auth_headers(staff_token)
    )

    assert get_response.status_code == 200
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Renamed by Organizer"

    delete_response = api_client.delete(f"/events/{event_id}", headers=_auth_headers(staff_token))
    assert delete_response.status_code == 204
