import uuid

from app.models import Entry, Pod


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_organizer_setup_flow_create_event_pod_entries(api_client, make_token, db_session):
    """Mirrors the PR2 UI flow: create Event -> create Pod (default swiss/generic
    slugs, matching EventDetail's hidden auto-fill) -> add walk-in Entries
    (generated player_uuid, source_system="opentourney-ui", per EntryRoster)."""
    organizer_token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    org_id = api_client.post(
        "/organizations", json={"name": "Test Org"}, headers=_auth_headers(organizer_token)
    ).json()["id"]

    event_response = api_client.post(
        "/events",
        json={"date": "2026-08-01", "name": "Test Event", "organization_id": org_id},
        headers=_auth_headers(organizer_token),
    )
    assert event_response.status_code == 201
    event_id = event_response.json()["id"]

    pod_response = api_client.post(
        "/pods",
        json={"event_id": event_id, "format_slug": "swiss", "game_slug": "generic"},
        headers=_auth_headers(organizer_token),
    )
    assert pod_response.status_code == 201
    pod_id = pod_response.json()["id"]

    entry_ids = []
    for display_name in ("Ash", "Misty"):
        entry_response = api_client.post(
            "/entries",
            json={
                "pod_id": pod_id,
                "player_uuid": str(uuid.uuid4()),
                "source_system": "opentourney-ui",
                "metadata": {"display_name": display_name},
            },
            headers=_auth_headers(organizer_token),
        )
        assert entry_response.status_code == 201
        entry_ids.append(entry_response.json()["id"])

    roster_response = api_client.get(
        "/entries", params={"pod_id": pod_id}, headers=_auth_headers(organizer_token)
    )
    assert roster_response.status_code == 200
    roster = roster_response.json()
    assert {row["id"] for row in roster} == set(entry_ids)
    assert {row["metadata"]["display_name"] for row in roster} == {"Ash", "Misty"}
    assert all(row["source_system"] == "opentourney-ui" for row in roster)

    persisted_entries = db_session.query(Entry).filter_by(pod_id=uuid.UUID(pod_id)).all()
    assert {str(entry.id) for entry in persisted_entries} == set(entry_ids)

    pod = db_session.get(Pod, uuid.UUID(pod_id))
    assert pod.format_slug == "swiss"
    assert pod.game_slug == "generic"
