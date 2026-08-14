import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    get_current_identity,
    org_member_role,
    require_organizer_claim,
    require_org_owner,
)
from app.auth.identity import Identity
from app.db import get_db_session
from app.models.organization import Organization, OrganizationMember, OrgRoleName
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationMemberCreate,
    OrganizationMemberRead,
    OrganizationRead,
)

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


@router.post("/{organization_id}/members", response_model=OrganizationMemberRead, status_code=201)
def add_organization_member(
    organization_id: uuid.UUID,
    payload: OrganizationMemberCreate,
    identity: Identity = Depends(require_org_owner),
    db: Session = Depends(get_db_session),
) -> OrganizationMember:
    member = OrganizationMember(
        organization_id=organization_id,
        player_uuid=payload.player_uuid,
        source_system=payload.source_system,
        role=payload.role,
    )
    db.add(member)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="this identity already has a role on this organization"
        ) from None
    db.refresh(member)
    return member


@router.get("/{organization_id}/members", response_model=list[OrganizationMemberRead])
def list_organization_members(
    organization_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> list[OrganizationMember]:
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="organization not found")
    role = org_member_role(db, identity, organization_id)
    if role not in (OrgRoleName.OWNER, OrgRoleName.ORGANIZER):
        raise HTTPException(
            status_code=403, detail="organizer role required for this organization"
        )
    return (
        db.query(OrganizationMember)
        .filter_by(organization_id=organization_id)
        .order_by(OrganizationMember.id)
        .all()
    )


@router.delete("/{organization_id}/members/{member_id}", status_code=204)
def revoke_organization_member(
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    identity: Identity = Depends(require_org_owner),
    db: Session = Depends(get_db_session),
) -> None:
    member = db.get(OrganizationMember, member_id)
    if member is None or member.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="organization member not found")
    if member.role == OrgRoleName.OWNER:
        # Lock the OWNER rows for this org within this transaction so a
        # concurrent revoke of a different OWNER member can't read the same
        # pre-delete count and also pass the <= 1 check (TOCTOU race). The
        # second transaction's own with_for_update() blocks until this one
        # commits/rolls back, then re-reads post-commit state.
        owner_rows = (
            db.query(OrganizationMember)
            .filter_by(organization_id=organization_id, role=OrgRoleName.OWNER)
            .with_for_update()
            .all()
        )
        if len(owner_rows) <= 1:
            raise HTTPException(
                status_code=409, detail="cannot revoke the organization's only owner"
            )
    db.delete(member)
    db.commit()
