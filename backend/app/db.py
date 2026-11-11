"""Database access for normal API requests.

get_tenant_db is the ONLY place request context is set (AGENTS.md rule 4).
Every route that touches tenant data depends on it. In one transaction it:

  1. verifies the bearer token (signature + expiry)        -> 401 if bad
  2. SET LOCAL ROLE agencydesk_api                           (RLS applies)
  3. sets app.agency_id + app.user_id from the token
  4. reads the caller's membership row *under RLS*
     (the "own row" branch of the agency_memberships read policy)
     WHERE removed_at IS NULL                               -> 401 if gone
  5. sets app.role + app.client_id from that row
  6. yields; COMMIT on success, ROLLBACK on any error

Everything uses SET LOCAL / set_config(..., true), so the settings vanish
when the transaction ends and a pooled connection can't carry one
request's identity into the next.
"""
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Connection, Engine, create_engine, text

from app.auth.tokens import InvalidToken, verify_session_token
from app.config import Settings

bearer = HTTPBearer(auto_error=False)

UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def create_api_engine(settings: Settings) -> Engine:
    """Pool for request traffic. Logs in as agencydesk_api, never the owner."""
    return create_engine(settings.api_database_url, pool_pre_ping=True)


@dataclass(frozen=True)
class TenantDb:
    """What a route gets: an open transaction with RLS context set, plus who
    the caller is (from the membership row, not from the request)."""

    conn: Connection
    agency_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    client_id: uuid.UUID | None

    @property
    def is_staff(self) -> bool:
        return self.role in ("agency_admin", "agency_member")


def _set_context(conn: Connection, key: str, value: str) -> None:
    # is_local = true: equivalent to SET LOCAL, cleared at transaction end.
    conn.execute(text("SELECT set_config(:key, :value, true)"), {"key": f"app.{key}", "value": value})


def get_tenant_db(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Iterator[TenantDb]:
    settings: Settings = request.app.state.settings
    engine: Engine = request.app.state.api_engine

    if credentials is None:
        raise UNAUTHORIZED
    try:
        claims = verify_session_token(credentials.credentials, settings.session_secret)
    except InvalidToken:
        raise UNAUTHORIZED from None

    with engine.connect() as conn, conn.begin():
        conn.execute(text("SET LOCAL ROLE agencydesk_api"))
        _set_context(conn, "agency_id", str(claims.agency_id))
        _set_context(conn, "user_id", str(claims.user_id))

        membership = conn.execute(
            text(
                """SELECT role, client_id FROM agency_memberships
                   WHERE agency_id = :agency_id AND user_id = :user_id AND removed_at IS NULL"""
            ),
            {"agency_id": claims.agency_id, "user_id": claims.user_id},
        ).one_or_none()
        if membership is None:
            raise UNAUTHORIZED  # removed, or never a member: the token is no longer good

        _set_context(conn, "role", membership.role)
        _set_context(conn, "client_id", str(membership.client_id or ""))

        yield TenantDb(
            conn=conn,
            agency_id=claims.agency_id,
            user_id=claims.user_id,
            role=membership.role,
            client_id=membership.client_id,
        )
