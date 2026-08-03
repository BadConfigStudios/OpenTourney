import uuid

from app.models import Pod
from app.models.rbac import PodRole


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


def _create_entry(api_client, token, pod_id: str) -> str:
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


def _add_pod_role_reader_token(db_session, make_token, pod_id: str) -> str:
    reader_uuid = uuid.uuid4()
    db_session.add(
        PodRole(
            pod_id=uuid.UUID(pod_id),
            player_uuid=reader_uuid,
            source_system="club-checkin",
            role="user",
        )
    )
    db_session.commit()
    return make_token(player_uuid=reader_uuid, source_system="club-checkin")


def test_organizer_creates_entry(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    player_uuid = str(uuid.uuid4())

    response = api_client.post(
        "/entries",
        json={
            "pod_id": pod_id,
            "player_uuid": player_uuid,
            "source_system": "club-checkin",
            "metadata": {"display_name": "Ash"},
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    assert response.json()["metadata"] == {"display_name": "Ash"}


def test_organizer_of_other_event_cannot_create_entry(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.post(
        "/entries",
        json={
            "pod_id": pod_id,
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "metadata": {},
        },
        headers=_auth_headers(stranger_token),
    )

    assert response.status_code == 403


def test_pod_creation_rejects_unknown_game_slug_with_422_not_500(api_client, make_token):
    # Pods validate game_slug at creation time (Task 13.5), so an unrecognized slug
    # is rejected at pod creation. This test ensures the registry lookup is validated
    # cleanly as a 422, not an unhandled ValueError -> 500.
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    ).json()["id"]

    # Pod creation with unknown game slug now rejects with 422
    response = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "unknown-game"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_entry_creation_rejects_pod_with_unregistered_game_slug_with_422_not_500(
    api_client, make_token, db_session
):
    # A pod's game_slug is validated against the registry at create/update time
    # (Task 13.5), but a slug that was valid when the pod was created can later
    # become unregistered (issue #22). entries.py's own _get_validated_game_module
    # is the safety net for that case, so bypass the router-level pod validation by
    # inserting the Pod row directly with an intentionally-unregistered game_slug.
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    event_id = api_client.post(
        "/events", json={"date": "2026-09-01"}, headers=_auth_headers(token)
    ).json()["id"]

    pod = Pod(event_id=uuid.UUID(event_id), format_slug="swiss", game_slug="pokemon-tcg")
    db_session.add(pod)
    db_session.commit()

    response = api_client.post(
        "/entries",
        json={
            "pod_id": str(pod.id),
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "metadata": {},
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 422


def test_pod_role_can_read_entries_without_organizer_row(api_client, make_token, db_session):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)
    api_client.post(
        "/entries",
        json={
            "pod_id": pod_id,
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "metadata": {},
        },
        headers=_auth_headers(owner_token),
    )

    reader_uuid = uuid.uuid4()
    db_session.add(
        PodRole(
            pod_id=uuid.UUID(pod_id),
            player_uuid=reader_uuid,
            source_system="club-checkin",
            role="user",
        )
    )
    db_session.commit()
    reader_token = make_token(player_uuid=reader_uuid, source_system="club-checkin")

    response = api_client.get(
        "/entries", params={"pod_id": pod_id}, headers=_auth_headers(reader_token)
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_organizer_can_update_and_delete_entry(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    entry_id = api_client.post(
        "/entries",
        json={
            "pod_id": pod_id,
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "metadata": {},
        },
        headers=_auth_headers(token),
    ).json()["id"]

    patch_response = api_client.patch(
        f"/entries/{entry_id}",
        json={"metadata": {"display_name": "Misty"}},
        headers=_auth_headers(token),
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["metadata"] == {"display_name": "Misty"}

    delete_response = api_client.delete(f"/entries/{entry_id}", headers=_auth_headers(token))
    assert delete_response.status_code == 204


def test_get_entry_as_organizer_returns_200(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    entry_id = _create_entry(api_client, token, pod_id)

    response = api_client.get(f"/entries/{entry_id}", headers=_auth_headers(token))

    assert response.status_code == 200
    assert response.json()["id"] == entry_id


def test_get_entry_as_pod_role_reader_returns_200(api_client, make_token, db_session):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)
    entry_id = _create_entry(api_client, owner_token, pod_id)

    reader_token = _add_pod_role_reader_token(db_session, make_token, pod_id)
    response = api_client.get(f"/entries/{entry_id}", headers=_auth_headers(reader_token))

    assert response.status_code == 200
    assert response.json()["id"] == entry_id


def test_get_entry_as_stranger_returns_403(api_client, make_token):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)
    entry_id = _create_entry(api_client, owner_token, pod_id)

    stranger_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    response = api_client.get(f"/entries/{entry_id}", headers=_auth_headers(stranger_token))

    assert response.status_code == 403


def test_patch_entry_as_pod_role_reader_returns_403(api_client, make_token, db_session):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)
    entry_id = _create_entry(api_client, owner_token, pod_id)

    reader_token = _add_pod_role_reader_token(db_session, make_token, pod_id)
    response = api_client.patch(
        f"/entries/{entry_id}",
        json={"metadata": {"display_name": "Brock"}},
        headers=_auth_headers(reader_token),
    )

    assert response.status_code == 403


def test_delete_entry_as_pod_role_reader_returns_403(api_client, make_token, db_session):
    owner_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, owner_token)
    entry_id = _create_entry(api_client, owner_token, pod_id)

    reader_token = _add_pod_role_reader_token(db_session, make_token, pod_id)
    response = api_client.delete(f"/entries/{entry_id}", headers=_auth_headers(reader_token))

    assert response.status_code == 403


def test_get_unknown_entry_returns_404(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.get(f"/entries/{uuid.uuid4()}", headers=_auth_headers(token))

    assert response.status_code == 404


def test_create_entry_with_unknown_pod_returns_404(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.post(
        "/entries",
        json={
            "pod_id": str(uuid.uuid4()),
            "player_uuid": str(uuid.uuid4()),
            "source_system": "club-checkin",
            "metadata": {},
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 404


def test_list_entries_with_unknown_pod_returns_404(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = api_client.get(
        "/entries", params={"pod_id": str(uuid.uuid4())}, headers=_auth_headers(token)
    )

    assert response.status_code == 404


def test_duplicate_entry_submission_is_rejected(api_client, make_token):
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])
    pod_id = _create_pod(api_client, token)
    payload = {
        "pod_id": pod_id,
        "player_uuid": str(uuid.uuid4()),
        "source_system": "club-checkin",
        "metadata": {},
    }
    api_client.post("/entries", json=payload, headers=_auth_headers(token))

    response = api_client.post("/entries", json=payload, headers=_auth_headers(token))

    assert response.status_code == 409
