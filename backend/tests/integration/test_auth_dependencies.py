import uuid
from datetime import date

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_identity, require_event_organizer, require_pod_access
from app.auth.identity import Identity
from app.config import get_settings
from app.db import get_db_session
from app.models import Event, Pod
from app.models.rbac import EventOrganizer, PodRole


def _build_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(identity: Identity = Depends(get_current_identity)) -> dict:  # noqa: B008
        return {"player_uuid": str(identity.player_uuid), "source_system": identity.source_system}

    @app.get("/events/{event_id}/organizer-only")
    def organizer_only(
        event_id: uuid.UUID,
        identity: Identity = Depends(require_event_organizer),  # noqa: B008
    ) -> dict:
        return {"ok": True}

    @app.get("/pods/{pod_id}/access-only")
    def access_only(
        pod_id: uuid.UUID,
        identity: Identity = Depends(require_pod_access),  # noqa: B008
    ) -> dict:
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


def test_tampered_token_is_rejected(db_session, test_settings, make_token):
    client = _client(_build_test_app(), db_session, test_settings)
    token = make_token(player_uuid=uuid.uuid4())

    response = client.get("/whoami", headers={"Authorization": f"Bearer {token}x"})

    assert response.status_code == 401


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
