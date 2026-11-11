"""Invite management for agency admins. Thin: parse, call the service.

Accepting an invite (POST /invites/accept) lives in routers/auth.py, because
it runs on the login-only database pool before the invitee has a tenant.
"""
import uuid

from fastapi import APIRouter, Depends, Request, Response, status

from app.db import TenantDb, get_tenant_db
from app.repositories.invites import InviteRow
from app.schemas.invites import InviteCreate, IssuedInviteResponse, StaffInvite
from app.services import invites as service
from app.services.invites import IssuedInvite

router = APIRouter(prefix="/invites", tags=["invites"])


def _staff_invite(row: InviteRow) -> StaffInvite:
    return StaffInvite(
        id=row.id, email=row.email, role=row.role, client_id=row.client_id, status=row.status,
        send_count=row.send_count, expires_at=row.expires_at, created_at=row.created_at,
    )


def _issued(result: IssuedInvite) -> IssuedInviteResponse:
    return IssuedInviteResponse(invite=_staff_invite(result.invite), invite_url=result.invite_url)


@router.get("", response_model=list[StaffInvite])
def list_invites(db: TenantDb = Depends(get_tenant_db)) -> list[StaffInvite]:
    return [_staff_invite(row) for row in service.list_invites(db)]


@router.post("", response_model=IssuedInviteResponse, status_code=status.HTTP_201_CREATED)
def create_invite(
    body: InviteCreate, request: Request, db: TenantDb = Depends(get_tenant_db)
) -> IssuedInviteResponse:
    return _issued(
        service.create_invite(db, request.app.state.settings, body.email, body.role, body.client_id)
    )


@router.post("/{invite_id}/resend", response_model=IssuedInviteResponse)
def resend_invite(
    invite_id: uuid.UUID, request: Request, db: TenantDb = Depends(get_tenant_db)
) -> IssuedInviteResponse:
    return _issued(service.resend_invite(db, request.app.state.settings, invite_id))


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(invite_id: uuid.UUID, db: TenantDb = Depends(get_tenant_db)) -> Response:
    service.revoke_invite(db, invite_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
