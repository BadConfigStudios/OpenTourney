from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_identity, require_organizer_claim
from app.auth.identity import Identity
from app.db import get_db_session
from app.models.organization import Organization, OrganizationMember, OrgRoleName
from app.schemas.organization import OrganizationCreate, OrganizationRead

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationRead, status_code=201)
def create_organization(
    payload: OrganizationCreate,
    identity: Identity = Depends(require_organizer_claim),
    db: Session = Depends(get_db_session),
) -> Organization:
    org = Organization(name=payload.name)
    db.add(org)
    db.flush()
    db.add(
        OrganizationMember(
            organization_id=org.id,
            player_uuid=identity.player_uuid,
            source_system=identity.source_system,
            role=OrgRoleName.OWNER,
        )
    )
    db.commit()
    db.refresh(org)
    return org


@router.get("", response_model=list[OrganizationRead])
def list_organizations(
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> list[Organization]:
    org_ids = {
        row.organization_id
        for row in db.query(OrganizationMember.organization_id).filter_by(
            player_uuid=identity.player_uuid, source_system=identity.source_system
        )
    }
    if not org_ids:
        return []
    return (
        db.query(Organization)
        .filter(Organization.id.in_(org_ids))
        .order_by(Organization.name, Organization.id)
        .all()
    )
