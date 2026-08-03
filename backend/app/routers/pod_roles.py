import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_pod_organizer
from app.auth.identity import Identity
from app.db import get_db_session
from app.models.rbac import PodRole
from app.schemas.pod_role import PodRoleCreate, PodRoleRead

router = APIRouter(prefix="/pods/{pod_id}/roles", tags=["pod-roles"])


@router.post("", response_model=PodRoleRead, status_code=201)
def assign_pod_role(
    pod_id: uuid.UUID,
    payload: PodRoleCreate,
    identity: Identity = Depends(require_pod_organizer),
    db: Session = Depends(get_db_session),
) -> PodRole:
    existing = (
        db.query(PodRole)
        .filter_by(
            pod_id=pod_id,
            player_uuid=payload.player_uuid,
            source_system=payload.source_system,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="this identity already has a role on this pod"
        )

    role = PodRole(
        pod_id=pod_id,
        player_uuid=payload.player_uuid,
        source_system=payload.source_system,
        role=payload.role,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.get("", response_model=list[PodRoleRead])
def list_pod_roles(
    pod_id: uuid.UUID,
    identity: Identity = Depends(require_pod_organizer),
    db: Session = Depends(get_db_session),
) -> list[PodRole]:
    return db.query(PodRole).filter_by(pod_id=pod_id).all()


@router.delete("/{role_id}", status_code=204)
def revoke_pod_role(
    pod_id: uuid.UUID,
    role_id: uuid.UUID,
    identity: Identity = Depends(require_pod_organizer),
    db: Session = Depends(get_db_session),
) -> None:
    role = db.get(PodRole, role_id)
    if role is None or role.pod_id != pod_id:
        raise HTTPException(status_code=404, detail="pod role not found")
    db.delete(role)
    db.commit()
