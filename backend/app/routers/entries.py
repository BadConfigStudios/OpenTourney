import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    event_organizer_exists,
    get_current_identity,
    pod_access_allowed,
    require_pod_access,
)
from app.auth.identity import Identity
from app.db import get_db_session
from app.games.base import GameModule
from app.games.registry import get_game_module
from app.models import Entry, Pod, Round
from app.schemas.entry import EntryCreate, EntryRead, EntryUpdate

router = APIRouter(prefix="/entries", tags=["entries"])


def _get_entry_or_404(db: Session, entry_id: uuid.UUID) -> Entry:
    """Lookup entry by ID; raise HTTPException(404) if not found."""
    entry = db.get(Entry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    return entry


def _require_pod_event_organizer(db: Session, identity: Identity, pod: Pod, detail: str) -> None:
    """Check organizer role for pod's event; raise HTTPException(403) if lacking."""
    if not event_organizer_exists(db, identity, pod.event_id):
        raise HTTPException(status_code=403, detail=detail)


def _get_validated_game_module(pod: Pod) -> GameModule:
    """Look up the game module for a pod's game_slug, or raise a diagnosable 422."""
    try:
        return get_game_module(pod.game_slug)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"pod's game_slug {pod.game_slug!r} is not a recognized game module",
        ) from exc


@router.post("", response_model=EntryRead, status_code=201)
def create_entry(
    payload: EntryCreate,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Entry:
    pod = db.get(Pod, payload.pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    _require_pod_event_organizer(
        db, identity, pod, "Organizer role required for this pod's event"
    )

    game_module = _get_validated_game_module(pod)
    try:
        game_module.validate_entry_metadata(payload.metadata)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = (
        db.query(Entry)
        .filter_by(
            pod_id=payload.pod_id,
            player_uuid=payload.player_uuid,
            source_system=payload.source_system,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="an entry for this player already exists on this pod"
        )

    entry = Entry(
        pod_id=payload.pod_id,
        player_uuid=payload.player_uuid,
        source_system=payload.source_system,
        metadata_=payload.metadata,
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="an entry for this player already exists on this pod"
        ) from None
    db.refresh(entry)
    return entry


@router.get("", response_model=list[EntryRead])
def list_entries(
    pod_id: uuid.UUID = Query(...),
    identity: Identity = Depends(require_pod_access),
    db: Session = Depends(get_db_session),
) -> list[Entry]:
    return db.query(Entry).filter_by(pod_id=pod_id).order_by(Entry.id).all()


@router.get("/{entry_id}", response_model=EntryRead)
def get_entry(
    entry_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Entry:
    entry = _get_entry_or_404(db, entry_id)
    if not pod_access_allowed(db, identity, entry.pod_id):
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
    _require_pod_event_organizer(
        db, identity, pod, "Organizer role required for this entry's pod's event"
    )

    merged_metadata = {**entry.metadata_, **payload.metadata}

    game_module = _get_validated_game_module(pod)
    try:
        game_module.validate_entry_metadata(merged_metadata)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    entry.metadata_ = merged_metadata
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
    _require_pod_event_organizer(
        db, identity, pod, "Organizer role required for this entry's pod's event"
    )
    db.delete(entry)
    db.commit()


@router.post("/{entry_id}/drop", response_model=EntryRead)
def drop_entry(
    entry_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Entry:
    entry = _get_entry_or_404(db, entry_id)
    pod = db.get(Pod, entry.pod_id)
    _require_pod_event_organizer(
        db, identity, pod, "Organizer role required for this entry's pod's event"
    )
    if entry.dropped_at_round is not None:
        raise HTTPException(status_code=409, detail="entry is already dropped")
    if pod.completed_at is not None:
        raise HTTPException(status_code=409, detail="pod is already complete")

    round_count = db.query(Round).filter_by(pod_id=entry.pod_id).count()
    entry.dropped_at_round = round_count
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/{entry_id}/undrop", response_model=EntryRead)
def undrop_entry(
    entry_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Entry:
    entry = _get_entry_or_404(db, entry_id)
    pod = db.get(Pod, entry.pod_id)
    _require_pod_event_organizer(
        db, identity, pod, "Organizer role required for this entry's pod's event"
    )
    if entry.dropped_at_round is None:
        raise HTTPException(status_code=409, detail="entry is not dropped")

    entry.dropped_at_round = None
    db.commit()
    db.refresh(entry)
    return entry
