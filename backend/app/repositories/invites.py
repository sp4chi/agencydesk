"""SQL for managing invites. Runs under get_tenant_db: RLS limits every
query to the caller's agency, and the invites `admin` policy limits writes
(and reads) to agency_admin. The WHERE clauses here are for correctness,
not security."""
import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import Connection, text

_COLUMNS = "id, email, role, client_id, status, send_count, expires_at, created_at"


@dataclass(frozen=True)
class InviteRow:
    id: uuid.UUID
    email: str
    role: str
    client_id: uuid.UUID | None
    status: str
    send_count: int
    expires_at: dt.datetime
    created_at: dt.datetime


def list_invites(conn: Connection) -> list[InviteRow]:
    rows = conn.execute(text(f"SELECT {_COLUMNS} FROM invites ORDER BY created_at DESC"))
    return [InviteRow(**r._asdict()) for r in rows]


def is_active_member(conn: Connection, email: str) -> bool:
    return conn.execute(
        text(
            """SELECT EXISTS (
                 SELECT 1 FROM agency_memberships m JOIN users u ON u.id = m.user_id
                 WHERE u.email = :email AND m.removed_at IS NULL)"""
        ),
        {"email": email},
    ).scalar_one()


def upsert_pending_invite(
    conn: Connection,
    agency_id: uuid.UUID,
    invited_by: uuid.UUID,
    email: str,
    role: str,
    client_id: uuid.UUID | None,
    token_hash: str,
    ttl_days: int,
) -> InviteRow:
    """Create, or re-send if a pending invite for this email exists: one row
    per (agency, email), and the new token hash replaces the old one, so
    the previous link stops working."""
    row = conn.execute(
        text(
            f"""INSERT INTO invites
                  (agency_id, email, role, client_id, token_hash, invited_by, expires_at)
                VALUES (:agency_id, :email, :role, :client_id, :token_hash, :invited_by,
                        now() + make_interval(days => :ttl_days))
                ON CONFLICT (agency_id, email) WHERE status = 'pending'
                DO UPDATE SET token_hash = EXCLUDED.token_hash,
                              role       = EXCLUDED.role,
                              client_id  = EXCLUDED.client_id,
                              invited_by = EXCLUDED.invited_by,
                              expires_at = EXCLUDED.expires_at,
                              send_count = invites.send_count + 1
                RETURNING {_COLUMNS}"""
        ),
        {
            "agency_id": agency_id, "email": email, "role": role, "client_id": client_id,
            "token_hash": token_hash, "invited_by": invited_by, "ttl_days": ttl_days,
        },
    ).one()
    return InviteRow(**row._asdict())


def resend_pending_invite(
    conn: Connection, invite_id: uuid.UUID, token_hash: str, ttl_days: int
) -> InviteRow | None:
    row = conn.execute(
        text(
            f"""UPDATE invites
                SET token_hash = :token_hash,
                    expires_at = now() + make_interval(days => :ttl_days),
                    send_count = send_count + 1
                WHERE id = :id AND status = 'pending'
                RETURNING {_COLUMNS}"""
        ),
        {"id": invite_id, "token_hash": token_hash, "ttl_days": ttl_days},
    ).one_or_none()
    return InviteRow(**row._asdict()) if row else None


def revoke_pending_invite(conn: Connection, invite_id: uuid.UUID) -> bool:
    result = conn.execute(
        text("UPDATE invites SET status = 'revoked' WHERE id = :id AND status = 'pending'"),
        {"id": invite_id},
    )
    return result.rowcount == 1


def invite_exists(conn: Connection, invite_id: uuid.UUID) -> bool:
    return conn.execute(
        text("SELECT EXISTS (SELECT 1 FROM invites WHERE id = :id)"), {"id": invite_id}
    ).scalar_one()
