"""SQL for GET /me. Runs under get_tenant_db, so RLS applies: the user,
agency and client rows are only visible because they belong to the caller."""
import uuid
from dataclasses import dataclass

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class MeRow:
    user_id: uuid.UUID
    email: str
    user_name: str
    agency_id: uuid.UUID
    agency_name: str
    client_id: uuid.UUID | None
    client_name: str | None


def load_me(
    conn: Connection, user_id: uuid.UUID, agency_id: uuid.UUID, client_id: uuid.UUID | None
) -> MeRow | None:
    # user_id / agency_id / client_id come from TenantDb (the membership
    # lookup in get_tenant_db), never from the request.
    row = conn.execute(
        text(
            """SELECT u.id AS user_id, u.email, u.name AS user_name,
                      a.id AS agency_id, a.name AS agency_name,
                      c.id AS client_id, c.name AS client_name
               FROM users u
               JOIN agencies a ON a.id = :agency_id
               LEFT JOIN clients c ON c.agency_id = a.id AND c.id = :client_id
               WHERE u.id = :user_id"""
        ),
        {"user_id": user_id, "agency_id": agency_id, "client_id": client_id},
    ).one_or_none()
    return MeRow(**row._asdict()) if row else None
