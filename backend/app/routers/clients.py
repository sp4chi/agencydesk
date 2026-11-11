"""Clients (customer companies). Staff read; admins create."""
import uuid

from fastapi import APIRouter, Depends, status

from app.db import TenantDb, get_tenant_db
from app.repositories.clients import ClientRow
from app.schemas.projects import ClientCreate, StaffClient
from app.services import clients as service

router = APIRouter(prefix="/clients", tags=["clients"])


def _staff_client(row: ClientRow) -> StaffClient:
    return StaffClient(id=row.id, name=row.name, created_at=row.created_at)


@router.get("", response_model=list[StaffClient])
def list_clients(db: TenantDb = Depends(get_tenant_db)) -> list[StaffClient]:
    return [_staff_client(row) for row in service.list_clients(db)]


@router.get("/{client_id}", response_model=StaffClient)
def get_client(client_id: uuid.UUID, db: TenantDb = Depends(get_tenant_db)) -> StaffClient:
    return _staff_client(service.get_client(db, client_id))


@router.post("", response_model=StaffClient, status_code=status.HTTP_201_CREATED)
def create_client(body: ClientCreate, db: TenantDb = Depends(get_tenant_db)) -> StaffClient:
    return _staff_client(service.create_client(db, body.name))
