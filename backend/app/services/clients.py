"""Client (customer company) rules. Staff only: the portal shows a client
user their own client through /me, so it needs nothing here."""
import uuid

from app.db import TenantDb
from app.errors import Forbidden, Invalid, NotFound
from app.repositories import clients as repository
from app.repositories.clients import ClientRow


def _require_staff(db: TenantDb) -> None:
    if not db.is_staff:
        raise Forbidden("Staff only")


def list_clients(db: TenantDb) -> list[ClientRow]:
    _require_staff(db)
    return repository.list_clients(db.conn)


def get_client(db: TenantDb, client_id: uuid.UUID) -> ClientRow:
    _require_staff(db)
    client = repository.get_client(db.conn, client_id)
    if client is None:
        raise NotFound()
    return client


def create_client(db: TenantDb, name: str) -> ClientRow:
    if db.role != "agency_admin":
        raise Forbidden("Only agency admins can create clients")
    name = name.strip()
    if not name:
        raise Invalid("Name is required")
    return repository.create_client(db.conn, db.agency_id, name)
