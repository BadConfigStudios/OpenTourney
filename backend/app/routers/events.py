import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_current_identity,
    org_member_role,
    require_event_organizer,
    require_organizer_claim,
    visible_event_ids,
)
from app.auth.identity import Identity
from app.db import get_db_session
from app.models import Event, Pod
from app.models.organization import OrgRoleName
from app.models.rbac import EventOrganizer
from app.routers.pods import delete_pod_children
from app.schemas.event import EventCreate, EventRead, EventUpdate

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=EventRead, status_code=201)
def create_event(
    payload: EventCreate,
    identity: Identity = Depends(require_organizer_claim),
    db: Session = Depends(get_db_session),
) -> Event:
    role = org_member_role(db, identity, payload.organization_id)
    if role not in (OrgRoleName.OWNER, OrgRoleName.ORGANIZER):
        raise HTTPException(
            status_code=403, detail="Owner or Organizer role required for this organization"
        )

    event = Event(
        date=payload.date,
        name=payload.name,
        description=payload.description,
        organization_id=payload.organization_id,
    )
    db.add(event)
    db.flush()
    db.add(
        EventOrganizer(
            event_id=event.id,
            player_uuid=identity.player_uuid,
            source_system=identity.source_system,
        )
    )
    db.commit()
    db.refresh(event)
    return event


@router.get("", response_model=list[EventRead])
def list_events(
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> list[Event]:
    ids = visible_event_ids(db, identity)
    if not ids:
        return []
    return db.query(Event).filter(Event.id.in_(ids)).order_by(Event.date, Event.id).all()


@router.get("/{event_id}", response_model=EventRead)
def get_event(
    event_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    if event_id not in visible_event_ids(db, identity):
        raise HTTPException(status_code=403, detail="no role scoped to this event")
    return event


@router.patch("/{event_id}", response_model=EventRead)
def update_event(
    event_id: uuid.UUID,
    payload: EventUpdate,
    identity: Identity = Depends(require_event_organizer),
    db: Session = Depends(get_db_session),
) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    updates = payload.model_dump(exclude_unset=True)
    # date/name are backed by NOT NULL columns; only description may be explicitly
    # nulled via PATCH. Without this check, an explicit `null` passes
    # Pydantic (the field IS set) and slips through to setattr below, which
    # then throws an uncaught IntegrityError at commit time.
    for field in ("date", "name"):
        if field in updates and updates[field] is None:
            raise HTTPException(status_code=422, detail=f"{field} cannot be null")
    # EventUpdate's field set (date, name, description) IS the whitelist for
    # what this loop may PATCH — anything added to that schema becomes
    # silently PATCH-able here, so new fields need deliberate consideration.
    for field, value in updates.items():
        setattr(event, field, value)
    db.commit()
    db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=204)
def delete_event(
    event_id: uuid.UUID,
    identity: Identity = Depends(require_event_organizer),
    db: Session = Depends(get_db_session),
) -> None:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")

    for pod in db.query(Pod).filter_by(event_id=event_id).all():
        delete_pod_children(db, pod.id)
        db.delete(pod)
    db.query(EventOrganizer).filter_by(event_id=event_id).delete()
    db.delete(event)
    db.commit()
