import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
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
from app.formats.registry import get_tournament_format
from app.games.registry import get_game_module
from app.models import Entry, Match, MatchResult, Pod, Round
from app.models.rbac import PodRole
from app.schemas.pod import PodCreate, PodRead, PodUpdate
from app.schemas.report import PodReport, StandingRowRead

router = APIRouter(prefix="/pods", tags=["pods"])


def _validate_game_slug(game_slug: str) -> None:
    """Validate that game_slug is a recognized game module, or raise HTTPException(422)."""
    try:
        get_game_module(game_slug)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"game_slug {game_slug!r} is not a recognized game module",
        ) from exc


@router.post("", response_model=PodRead, status_code=201)
def create_pod(
    payload: PodCreate,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Pod:
    if not event_organizer_exists(db, identity, payload.event_id):
        raise HTTPException(status_code=403, detail="Organizer role required for this event")

    _validate_game_slug(payload.game_slug)

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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="event already has a pod; v1 supports exactly one pod per event",
        ) from None
    db.refresh(pod)
    return pod


@router.get("", response_model=list[PodRead])
def list_pods(
    event_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> list[Pod]:
    if event_id not in visible_event_ids(db, identity):
        raise HTTPException(status_code=403, detail="no role scoped to this event")
    return db.query(Pod).filter_by(event_id=event_id).order_by(Pod.id).all()


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
    _validate_game_slug(payload.game_slug)
    pod.format_slug = payload.format_slug
    pod.game_slug = payload.game_slug
    db.commit()
    db.refresh(pod)
    return pod


def _round_fully_reported(round_: Round) -> bool:
    return all(
        match.entry2_id is None or match.result != MatchResult.UNREPORTED
        for match in round_.matches
    )


@router.post("/{pod_id}/complete", response_model=PodRead)
def complete_pod(
    pod_id: uuid.UUID,
    identity: Identity = Depends(require_pod_organizer),
    db: Session = Depends(get_db_session),
) -> Pod:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    if pod.completed_at is not None:
        raise HTTPException(status_code=409, detail="pod already complete")

    rounds = db.query(Round).filter_by(pod_id=pod_id).order_by(Round.number).all()
    if rounds and not _round_fully_reported(rounds[-1]):
        raise HTTPException(
            status_code=409,
            detail=f"round {rounds[-1].number} has an unreported match; cannot complete pod",
        )

    pod.completed_at = func.now()
    db.commit()
    db.refresh(pod)
    return pod


@router.get("/{pod_id}/report", response_model=PodReport)
def get_pod_report(
    pod_id: uuid.UUID,
    identity: Identity = Depends(require_pod_access),
    db: Session = Depends(get_db_session),
) -> PodReport:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")

    try:
        tournament_format = get_tournament_format(pod.format_slug)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"pod's format_slug {pod.format_slug!r} is not a recognized tournament format",
        ) from exc

    all_entries = db.query(Entry).filter_by(pod_id=pod_id).order_by(Entry.id).all()
    all_rounds = db.query(Round).filter_by(pod_id=pod_id).order_by(Round.number).all()

    usable_rounds = all_rounds
    is_partial = False
    if usable_rounds and not _round_fully_reported(usable_rounds[-1]):
        usable_rounds = usable_rounds[:-1]
        is_partial = True

    standings = tournament_format.compute_standings(all_entries, usable_rounds)

    return PodReport(
        is_complete=pod.completed_at is not None,
        rounds_played=len(all_rounds),
        is_partial=is_partial,
        standings=[
            StandingRowRead(entry_id=row.entry_id, points=row.points, rank=row.rank)
            for row in standings
        ],
    )


def delete_pod_children(db: Session, pod_id: uuid.UUID) -> None:
    for round_ in db.query(Round).filter_by(pod_id=pod_id).all():
        db.query(Match).filter_by(round_id=round_.id).delete()
    db.query(Round).filter_by(pod_id=pod_id).delete()
    db.query(Entry).filter_by(pod_id=pod_id).delete()
    db.query(PodRole).filter_by(pod_id=pod_id).delete()


@router.delete("/{pod_id}", status_code=204)
def delete_pod(
    pod_id: uuid.UUID,
    identity: Identity = Depends(require_pod_organizer),
    db: Session = Depends(get_db_session),
) -> None:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")

    delete_pod_children(db, pod_id)
    db.delete(pod)
    db.commit()
