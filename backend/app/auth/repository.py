"""SQL for login and agency selection. Runs on the auth pool (no RLS), so
every query here filters by the user_id explicitly and returns only that
user's own rows."""
import uuid
from dataclasses import dataclass

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class UserCredentials:
    id: uuid.UUID
    password_hash: str


@dataclass(frozen=True)
class MembershipRow:
    agency_id: uuid.UUID
    agency_name: str
    role: str
    client_name: str | None


_MEMBERSHIPS_SQL = """
    SELECT m.agency_id, a.name AS agency_name, m.role, c.name AS client_name
    FROM agency_memberships m
    JOIN agencies a ON a.id = m.agency_id
    LEFT JOIN clients c ON c.agency_id = m.agency_id AND c.id = m.client_id
    WHERE m.user_id = :user_id
      AND m.removed_at IS NULL
      AND m.is_staff = :is_staff
"""


def find_user_by_email(conn: Connection, email: str) -> UserCredentials | None:
    row = conn.execute(
        text("SELECT id, password_hash FROM users WHERE email = :email"), {"email": email}
    ).one_or_none()
    return UserCredentials(id=row.id, password_hash=row.password_hash) if row else None


def active_memberships(conn: Connection, user_id: uuid.UUID, is_staff: bool) -> list[MembershipRow]:
    rows = conn.execute(
        text(_MEMBERSHIPS_SQL + " ORDER BY a.name"), {"user_id": user_id, "is_staff": is_staff}
    )
    return [MembershipRow(**row._asdict()) for row in rows]


def active_membership(
    conn: Connection, user_id: uuid.UUID, agency_id: uuid.UUID, is_staff: bool
) -> MembershipRow | None:
    row = conn.execute(
        text(_MEMBERSHIPS_SQL + " AND m.agency_id = :agency_id"),
        {"user_id": user_id, "is_staff": is_staff, "agency_id": agency_id},
    ).one_or_none()
    return MembershipRow(**row._asdict()) if row else None
