import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import require_pod_access, require_pod_organizer
from app.auth.identity import Identity
from app.db import get_db_session
from app.models import Entry, Match, Pod, Round
from app.ruleset import get_ruleset_or_422
from app.schemas.round import RoundRead

router = APIRouter(prefix="/pods/{pod_id}/rounds", tags=["rounds"])


def _get_pod_or_404(db: Session, pod_id: uuid.UUID) -> Pod:
    pod = db.get(Pod, pod_id)
    if pod is None:
        raise HTTPException(status_code=404, detail="pod not found")
    return pod


@router.post("", response_model=RoundRead, status_code=201)
def generate_round(
    pod_id: uuid.UUID,
    identity: Identity = Depends(require_pod_organizer),
    db: Session = Depends(get_db_session),
) -> Round:
    pod = _get_pod_or_404(db, pod_id)
    if pod.completed_at is not None:
        raise HTTPException(status_code=409, detail="pod is already complete")

    tournament_format = get_ruleset_or_422(pod).format

    entries = db.query(Entry).filter_by(pod_id=pod_id).order_by(Entry.id).all()
    if not entries:
        raise HTTPException(status_code=409, detail="pod has no entries")

    active_entries = [entry for entry in entries if entry.dropped_at_round is None]
    if not active_entries:
        raise HTTPException(status_code=409, detail="pod has no active entries")

    previous_rounds = db.query(Round).filter_by(pod_id=pod_id).order_by(Round.number).all()

    try:
        pairings = tournament_format.generate_round(
            entries=entries, previous_rounds=previous_rounds
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    round_ = Round(pod_id=pod_id, number=len(previous_rounds) + 1)
    db.add(round_)

    try:
        db.flush()

        for pairing in pairings:
            db.add(
                Match(
                    round_id=round_.id,
                    entry1_id=pairing.entry1_id,
                    entry2_id=pairing.entry2_id,
                    table_number=pairing.table_number,
                )
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="round already generated for this pod"
        ) from None
    db.refresh(round_)
    return round_


@router.get("", response_model=list[RoundRead])
def list_rounds(
    pod_id: uuid.UUID,
    identity: Identity = Depends(require_pod_access),
    db: Session = Depends(get_db_session),
) -> list[Round]:
    return db.query(Round).filter_by(pod_id=pod_id).order_by(Round.number).all()
