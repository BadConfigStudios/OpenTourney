import uuid
from datetime import date

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import (
    get_current_identity,
    get_jwks_provider,
    pod_staff_allowed,
    require_event_organizer,
    require_organizer_claim,
    require_pod_access,
    require_pod_organizer,
    visible_event_ids,
)
from app.auth.identity import Identity
from app.config import get_settings
from app.db import get_db_session
from app.models import Event, Pod
from app.models.rbac import EventOrganizer, PodRole, PodRoleName
from tests.support.fake_jwks import FakeUnreachableJWKSProvider


def _build_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(identity: Identity = Depends(get_current_identity)) -> dict:
        return {"player_uuid": str(identity.player_uuid), "source_system": identity.source_system}

    @app.get("/organizer-claim-only")
    def organizer_claim_only(identity: Identity = Depends(require_organizer_claim)) -> dict:
        return {"ok": True}

    @app.get("/events/{event_id}/organizer-only")
    def organizer_only(
        event_id: uuid.UUID, identity: Identity = Depends(require_event_organizer)
    ) -> dict:
        return {"ok": True}

    @app.get("/pods/{pod_id}/pod-organizer-only")
    def pod_organizer_only(
        pod_id: uuid.UUID, identity: Identity = Depends(require_pod_organizer)
    ) -> dict:
        return {"ok": True}

    @app.get("/pods/{pod_id}/access-only")
    def access_only(pod_id: uuid.UUID, identity: Identity = Depends(require_pod_access)) -> dict:
        return {"ok": True}

    return app


def _client(app: FastAPI, db_session, settings) -> TestClient:
    def override_get_db_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_valid_token_resolves_identity(db_session, test_settings, make_token):
    client = _client(_build_test_app(), db_session, test_settings)
    player_uuid = uuid.uuid4()
    token = make_token(player_uuid=player_uuid, source_system="club-checkin")

    response = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "player_uuid": str(player_uuid),
        "source_system": "club-checkin",
    }


def test_missing_token_is_rejected(db_session, test_settings):
    client = _client(_build_test_app(), db_session, test_settings)

    response = client.get("/whoami")

    # HTTPBearer's own missing-credentials response. NOTE: the brief expected 403 here,
    # citing historical FastAPI behavior, but the installed fastapi==0.141.1 (satisfying
    # this repo's `fastapi>=0.115` pin) raises 401 "Not authenticated" for a missing
    # Authorization header before our dependency chain ever runs. Verified with a
    # minimal repro against HTTPBearer directly. See task-6-report.md for details.
    assert response.status_code == 401


def test_unreachable_jwks_source_is_reported_as_service_unavailable(
    db_session, test_settings, make_token
):
    app = _build_test_app()
    client = _client(app, db_session, test_settings)
    app.dependency_overrides[get_jwks_provider] = lambda: FakeUnreachableJWKSProvider()
    token = make_token(player_uuid=uuid.uuid4())

    response = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 503


def test_tampered_token_is_rejected(db_session, test_settings, make_token):
    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=uuid.uuid4())

    response = client.get("/whoami", headers={"Authorization": f"Bearer {token}x"})

    assert response.status_code == 401


def test_organizer_claim_grants_access(db_session, test_settings, make_token):
    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=uuid.uuid4(), roles=["organizer"])

    response = client.get("/organizer-claim-only", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200


def test_missing_organizer_claim_is_forbidden(db_session, test_settings, make_token):
    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=uuid.uuid4())

    response = client.get("/organizer-claim-only", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


def test_event_organizer_row_grants_access(db_session, test_settings, make_token):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    player_uuid = uuid.uuid4()
    db_session.add(
        EventOrganizer(event_id=event.id, player_uuid=player_uuid, source_system="club-checkin")
    )
    db_session.commit()

    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=player_uuid, source_system="club-checkin")

    response = client.get(
        f"/events/{event.id}/organizer-only", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200


def test_no_event_organizer_row_is_forbidden(db_session, test_settings, make_token):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.commit()

    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=uuid.uuid4(), source_system="club-checkin")

    response = client.get(
        f"/events/{event.id}/organizer-only", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403


def test_nonexistent_event_is_not_found_for_event_organizer(db_session, test_settings, make_token):
    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=uuid.uuid4(), source_system="club-checkin")

    response = client.get(
        f"/events/{uuid.uuid4()}/organizer-only", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


def test_event_organizer_row_grants_pod_organizer_access(db_session, test_settings, make_token):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    player_uuid = uuid.uuid4()
    db_session.add(
        EventOrganizer(event_id=event.id, player_uuid=player_uuid, source_system="club-checkin")
    )
    db_session.commit()

    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=player_uuid, source_system="club-checkin")

    response = client.get(
        f"/pods/{pod.id}/pod-organizer-only", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200


def test_no_event_organizer_row_is_forbidden_for_pod_organizer(
    db_session, test_settings, make_token
):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.commit()

    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=uuid.uuid4(), source_system="club-checkin")

    response = client.get(
        f"/pods/{pod.id}/pod-organizer-only", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403


def test_nonexistent_pod_is_not_found_for_pod_organizer(db_session, test_settings, make_token):
    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=uuid.uuid4(), source_system="club-checkin")

    response = client.get(
        f"/pods/{uuid.uuid4()}/pod-organizer-only", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


def test_pod_role_grants_pod_access_without_organizer_row(db_session, test_settings, make_token):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    player_uuid = uuid.uuid4()
    db_session.add(
        PodRole(pod_id=pod.id, player_uuid=player_uuid, source_system="club-checkin", role="user")
    )
    db_session.commit()

    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=player_uuid, source_system="club-checkin")

    response = client.get(
        f"/pods/{pod.id}/access-only", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200


def test_no_role_at_all_is_forbidden_for_pod_access(db_session, test_settings, make_token):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.commit()

    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=uuid.uuid4(), source_system="club-checkin")

    response = client.get(
        f"/pods/{pod.id}/access-only", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403


def test_nonexistent_pod_is_not_found_for_pod_access(db_session, test_settings, make_token):
    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=uuid.uuid4(), source_system="club-checkin")

    response = client.get(
        f"/pods/{uuid.uuid4()}/access-only", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


def test_visible_event_ids_unions_organizer_and_pod_role_events(db_session):
    event_a = Event(date=date(2026, 9, 1))
    event_b = Event(date=date(2026, 9, 2))
    db_session.add_all([event_a, event_b])
    db_session.flush()

    player_uuid = uuid.uuid4()
    source_system = "club-checkin"

    # Organizer on event A.
    db_session.add(
        EventOrganizer(event_id=event_a.id, player_uuid=player_uuid, source_system=source_system)
    )

    # Pod role on a pod belonging to event B (no EventOrganizer row for B).
    pod = Pod(event_id=event_b.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    db_session.add(
        PodRole(pod_id=pod.id, player_uuid=player_uuid, source_system=source_system, role="user")
    )
    db_session.commit()

    identity = Identity(
        player_uuid=player_uuid, source_system=source_system, has_organizer_claim=False
    )

    result = visible_event_ids(db_session, identity)

    assert result == {event_a.id, event_b.id}


def test_visible_event_ids_returns_empty_set_when_no_roles(db_session):
    identity = Identity(
        player_uuid=uuid.uuid4(), source_system="club-checkin", has_organizer_claim=False
    )

    result = visible_event_ids(db_session, identity)

    assert result == set()


def test_pod_staff_allowed_true_for_event_organizer(db_session):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    player_uuid = uuid.uuid4()
    db_session.add(
        EventOrganizer(event_id=event.id, player_uuid=player_uuid, source_system="club-checkin")
    )
    db_session.commit()
    identity = Identity(player_uuid=player_uuid, source_system="club-checkin", has_organizer_claim=False)

    assert pod_staff_allowed(db_session, identity, pod.id) is True


def test_pod_staff_allowed_true_for_scorekeeper(db_session):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    player_uuid = uuid.uuid4()
    db_session.add(
        PodRole(
            pod_id=pod.id,
            player_uuid=player_uuid,
            source_system="club-checkin",
            role=PodRoleName.SCOREKEEPER,
        )
    )
    db_session.commit()
    identity = Identity(player_uuid=player_uuid, source_system="club-checkin", has_organizer_claim=False)

    assert pod_staff_allowed(db_session, identity, pod.id) is True


def test_pod_staff_allowed_false_for_plain_user_role(db_session):
    event = Event(date=date(2026, 9, 1))
    db_session.add(event)
    db_session.flush()
    pod = Pod(event_id=event.id, format_slug="swiss", game_slug="generic")
    db_session.add(pod)
    db_session.flush()
    player_uuid = uuid.uuid4()
    db_session.add(
        PodRole(
            pod_id=pod.id,
            player_uuid=player_uuid,
            source_system="club-checkin",
            role=PodRoleName.USER,
        )
    )
    db_session.commit()
    identity = Identity(player_uuid=player_uuid, source_system="club-checkin", has_organizer_claim=False)

    assert pod_staff_allowed(db_session, identity, pod.id) is False


def test_pod_staff_allowed_false_for_nonexistent_pod(db_session):
    identity = Identity(player_uuid=uuid.uuid4(), source_system="club-checkin", has_organizer_claim=False)

    assert pod_staff_allowed(db_session, identity, uuid.uuid4()) is False
