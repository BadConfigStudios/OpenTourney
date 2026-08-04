import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_identity, pod_staff_allowed
from app.auth.identity import Identity
from app.db import get_db_session
from app.models import Match, Round
from app.schemas.match import MatchRead, MatchResultUpdate

router = APIRouter(prefix="/matches", tags=["matches"])


def _get_match_or_404(db: Session, match_id: uuid.UUID) -> Match:
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="match not found")
    return match


def _require_pod_staff(db: Session, identity: Identity, pod_id: uuid.UUID) -> None:
    """Check Organizer-or-Scorekeeper for the given pod; raise HTTPException(403) if lacking."""
    if not pod_staff_allowed(db, identity, pod_id):
        raise HTTPException(status_code=403, detail="Organizer or Scorekeeper role required")


@router.post("/{match_id}/result", response_model=MatchRead)
def report_match_result(
    match_id: uuid.UUID,
    payload: MatchResultUpdate,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Match:
    match = _get_match_or_404(db, match_id)
    round_ = db.get(Round, match.round_id)
    _require_pod_staff(db, identity, round_.pod_id)

    if match.entry2_id is None:
        raise HTTPException(status_code=409, detail="bye matches do not require a result")

    reporter = f"{identity.source_system}:{identity.player_uuid}"
    match.result = payload.result
    match.reported_by = reporter
    match.witnessed_by = reporter
    db.commit()
    db.refresh(match)
    return match
