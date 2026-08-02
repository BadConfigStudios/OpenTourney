import uuid

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.identity import Identity, identity_from_claims
from app.auth.jwks import JWKSProvider, build_jwks_provider
from app.auth.oidc import AuthError, decode_token
from app.config import Settings, get_settings
from app.db import get_db_session
from app.models.pod import Pod
from app.models.rbac import EventOrganizer, PodRole

_bearer_scheme = HTTPBearer()


def get_jwks_provider(settings: Settings = Depends(get_settings)) -> JWKSProvider:  # noqa: B008
    return build_jwks_provider(settings)


def get_current_identity(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
    jwks_provider: JWKSProvider = Depends(get_jwks_provider),  # noqa: B008
) -> Identity:
    try:
        claims = decode_token(credentials.credentials, settings, jwks_provider)
        return identity_from_claims(claims)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def require_organizer_claim(
    identity: Identity = Depends(get_current_identity),  # noqa: B008
) -> Identity:
    if not identity.has_organizer_claim:
        raise HTTPException(status_code=403, detail="organizer claim required")
    return identity


def event_organizer_exists(db: Session, identity: Identity, event_id: uuid.UUID) -> bool:
    return (
        db.query(EventOrganizer)
        .filter_by(
            event_id=event_id,
            player_uuid=identity.player_uuid,
            source_system=identity.source_system,
        )
        .first()
        is not None
    )


def pod_role_exists(db: Session, identity: Identity, pod_id: uuid.UUID) -> bool:
    return (
        db.query(PodRole)
        .filter_by(
            pod_id=pod_id,
            player_uuid=identity.player_uuid,
            source_system=identity.source_system,
        )
        .first()
        is not None
    )


def visible_event_ids(db: Session, identity: Identity) -> set[uuid.UUID]:
    organizer_ids = {
        row.event_id
        for row in db.query(EventOrganizer.event_id).filter_by(
            player_uuid=identity.player_uuid, source_system=identity.source_system
        )
    }
    pod_ids = {
        row.pod_id
        for row in db.query(PodRole.pod_id).filter_by(
            player_uuid=identity.player_uuid, source_system=identity.source_system
        )
    }
    pod_event_ids = (
        {row.event_id for row in db.query(Pod.event_id).filter(Pod.id.in_(pod_ids))}
        if pod_ids
        else set()
    )
    return organizer_ids | pod_event_ids


def require_event_organizer(
    event_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db_session),  # noqa: B008
) -> Identity:
    if not event_organizer_exists(db, identity, event_id):
        raise HTTPException(status_code=403, detail="Organizer role required for this event")
    return identity


def require_pod_organizer(
    pod_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db_session),  # noqa: B008
) -> Identity:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    if not event_organizer_exists(db, identity, pod.event_id):
        raise HTTPException(
            status_code=403, detail="Organizer role required for this pod's event"
        )
    return identity


def require_pod_access(
    pod_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),  # noqa: B008
    db: Session = Depends(get_db_session),  # noqa: B008
) -> Identity:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    if not (
        event_organizer_exists(db, identity, pod.event_id)
        or pod_role_exists(db, identity, pod_id)
    ):
        raise HTTPException(status_code=403, detail="no role scoped to this pod")
    return identity
