"""The login-only database pool (agencydesk_auth, which has BYPASSRLS).

AGENTS.md rule 10: this pool is used ONLY by login, agency selection and
app.accept_invite, because those run before any tenant is known. Nothing
outside app/auth/ and the auth router may import it;
tests/test_api.py::test_auth_pool_is_only_used_by_auth_code enforces that.

Its grants are tiny (SELECT on users, agency_memberships, agencies,
clients; EXECUTE on app.accept_invite), and get_auth_db additionally opens
the transaction READ ONLY, so even a bug in login code can't write.
"""
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Connection, Engine, create_engine, text

from app.config import Settings


def create_auth_engine(settings: Settings) -> Engine:
    return create_engine(settings.auth_database_url, pool_pre_ping=True, pool_size=2)


def get_auth_db(request: Request) -> Iterator[Connection]:
    """Read-only transaction on the auth pool, for login and agency selection."""
    engine: Engine = request.app.state.auth_engine
    with engine.connect() as conn, conn.begin():
        conn.execute(text("SET TRANSACTION READ ONLY"))
        yield conn


def get_auth_db_for_invite_accept(request: Request) -> Iterator[Connection]:
    """Writable transaction on the auth pool, for POST /invites/accept only.

    It has to be writable because app.accept_invite inserts the user and
    membership. agencydesk_auth itself has no INSERT/UPDATE grants, so the
    only write it can make is through that function, which checks the token,
    the lock and who is logged in.
    """
    engine: Engine = request.app.state.auth_engine
    with engine.connect() as conn, conn.begin():
        yield conn
