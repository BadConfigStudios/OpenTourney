import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    event_organizer_exists,
    get_current_identity,
    pod_role_exists,
    require_pod_access,
)
from app.auth.identity import Identity
from app.db import get_db_session
from app.games.registry import get_game_module
from app.models import Entry, Pod
from app.schemas.entry import EntryCreate, EntryRead, EntryUpdate

router = APIRouter(prefix="/entries", tags=["entries"])


def _get_entry_or_404(db: Session, entry_id: uuid.UUID) -> Entry:
    """Lookup entry by ID; raise HTTPException(404) if not found."""
    entry = db.get(Entry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    return entry


def _require_event_organizer(db: Session, identity: Identity, pod: Pod, detail: str) -> None:
    """Check organizer role for pod's event; raise HTTPException(403) if lacking."""
    if not event_organizer_exists(db, identity, pod.event_id):
        raise HTTPException(status_code=403, detail=detail)


@router.post("", response_model=EntryRead, status_code=201)
def create_entry(
    payload: EntryCreate,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Entry:
    pod = db.get(Pod, payload.pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    _require_event_organizer(db, identity, pod, "Organizer role required for this pod's event")

    try:
        game_module = get_game_module(pod.game_slug)
        game_module.validate_entry_metadata(payload.metadata)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    entry = Entry(
        pod_id=payload.pod_id,
        player_uuid=payload.player_uuid,
        source_system=payload.source_system,
        metadata_=payload.metadata,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("", response_model=list[EntryRead])
def list_entries(
    pod_id: uuid.UUID = Query(...),
    identity: Identity = Depends(require_pod_access),
    db: Session = Depends(get_db_session),
) -> list[Entry]:
    return db.query(Entry).filter_by(pod_id=pod_id).all()


@router.get("/{entry_id}", response_model=EntryRead)
def get_entry(
    entry_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Entry:
    entry = _get_entry_or_404(db, entry_id)
    pod = db.get(Pod, entry.pod_id)
    if not (
        event_organizer_exists(db, identity, pod.event_id)
        or pod_role_exists(db, identity, entry.pod_id)
    ):
        raise HTTPException(status_code=403, detail="no role scoped to this entry's pod")
    return entry


@router.patch("/{entry_id}", response_model=EntryRead)
def update_entry(
    entry_id: uuid.UUID,
    payload: EntryUpdate,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Entry:
    entry = _get_entry_or_404(db, entry_id)
    pod = db.get(Pod, entry.pod_id)
    _require_event_organizer(db, identity, pod, "Organizer role required for this entry's pod's event")

    try:
        game_module = get_game_module(pod.game_slug)
        game_module.validate_entry_metadata(payload.metadata)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    entry.metadata_ = payload.metadata
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_entry(
    entry_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> None:
    entry = _get_entry_or_404(db, entry_id)
    pod = db.get(Pod, entry.pod_id)
    _require_event_organizer(db, identity, pod, "Organizer role required for this entry's pod's event")
    db.delete(entry)
    db.commit()
