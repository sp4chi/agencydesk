"""SQL for clients. Runs under get_tenant_db: RLS (app.can_see_client)
decides which rows exist for the caller."""
import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class ClientRow:
    id: uuid.UUID
    name: str
    created_at: dt.datetime


def list_clients(conn: Connection) -> list[ClientRow]:
    rows = conn.execute(text("SELECT id, name, created_at FROM clients ORDER BY name"))
    return [ClientRow(**r._asdict()) for r in rows]


def get_client(conn: Connection, client_id: uuid.UUID) -> ClientRow | None:
    row = conn.execute(
        text("SELECT id, name, created_at FROM clients WHERE id = :id"), {"id": client_id}
    ).one_or_none()
    return ClientRow(**row._asdict()) if row else None


def create_client(conn: Connection, agency_id: uuid.UUID, name: str) -> ClientRow:
    row = conn.execute(
        text(
            """INSERT INTO clients (agency_id, name) VALUES (:agency_id, :name)
               RETURNING id, name, created_at"""
        ),
        {"agency_id": agency_id, "name": name},
    ).one()
    return ClientRow(**row._asdict())
