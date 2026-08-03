# backend/app/routers/pods.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    event_organizer_exists,
    get_current_identity,
    require_pod_access,
    require_pod_organizer,
    visible_event_ids,
)
from app.auth.identity import Identity
from app.db import get_db_session
from app.models import Entry, Match, Pod, Round
from app.models.rbac import PodRole
from app.schemas.pod import PodCreate, PodRead, PodUpdate

router = APIRouter(prefix="/pods", tags=["pods"])


@router.post("", response_model=PodRead, status_code=201)
def create_pod(
    payload: PodCreate,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Pod:
    if not event_organizer_exists(db, identity, payload.event_id):
        raise HTTPException(status_code=403, detail="Organizer role required for this event")

    existing = db.query(Pod).filter_by(event_id=payload.event_id).first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="event already has a pod; v1 supports exactly one pod per event",
        )

    pod = Pod(
        event_id=payload.event_id,
        format_slug=payload.format_slug,
        game_slug=payload.game_slug,
    )
    db.add(pod)
    db.commit()
    db.refresh(pod)
    return pod


@router.get("", response_model=list[PodRead])
def list_pods(
    event_id: uuid.UUID = Query(...),
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> list[Pod]:
    if event_id not in visible_event_ids(db, identity):
        raise HTTPException(status_code=403, detail="no role scoped to this event")
    return db.query(Pod).filter_by(event_id=event_id).all()


@router.get("/{pod_id}", response_model=PodRead)
def get_pod(
    pod_id: uuid.UUID,
    identity: Identity = Depends(require_pod_access),
    db: Session = Depends(get_db_session),
) -> Pod:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    return pod


@router.patch("/{pod_id}", response_model=PodRead)
def update_pod(
    pod_id: uuid.UUID,
    payload: PodUpdate,
    identity: Identity = Depends(require_pod_organizer),
    db: Session = Depends(get_db_session),
) -> Pod:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    pod.format_slug = payload.format_slug
    pod.game_slug = payload.game_slug
    db.commit()
    db.refresh(pod)
    return pod


@router.delete("/{pod_id}", status_code=204)
def delete_pod(
    pod_id: uuid.UUID,
    identity: Identity = Depends(require_pod_organizer),
    db: Session = Depends(get_db_session),
) -> None:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")

    for round_ in db.query(Round).filter_by(pod_id=pod_id).all():
        db.query(Match).filter_by(round_id=round_.id).delete()
    db.query(Round).filter_by(pod_id=pod_id).delete()
    db.query(Entry).filter_by(pod_id=pod_id).delete()
    db.query(PodRole).filter_by(pod_id=pod_id).delete()
    db.delete(pod)
    db.commit()
