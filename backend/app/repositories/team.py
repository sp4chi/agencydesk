"""SQL for the agency's staff list. Runs under get_tenant_db: RLS limits it
to the caller's agency (the agency_memberships read policy lets staff see
the whole team)."""
import uuid
from dataclasses import dataclass

from sqlalchemy import Connection, text


@dataclass(frozen=True)
class TeamMemberRow:
    user_id: uuid.UUID
    name: str
    email: str
    role: str


def list_active_staff(conn: Connection) -> list[TeamMemberRow]:
    rows = conn.execute(
        text(
            """SELECT m.user_id, u.name, u.email, m.role
               FROM agency_memberships m
               JOIN users u ON u.id = m.user_id
               WHERE m.is_staff AND m.removed_at IS NULL
               ORDER BY u.name"""
        )
    )
    return [TeamMemberRow(**r._asdict()) for r in rows]
