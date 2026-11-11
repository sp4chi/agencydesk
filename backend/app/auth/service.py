"""Login and agency selection rules. No HTTP here: the router maps the
exceptions below to status codes."""
import uuid
from dataclasses import dataclass

from sqlalchemy import Connection

from app.auth import repository
from app.auth.passwords import verify_password
from app.auth.repository import MembershipRow
from app.auth.tokens import IdentityClaims, LoginKind, issue_identity_token, issue_session_token
from app.config import Settings


class InvalidCredentials(Exception):
    """Unknown email or wrong password. Deliberately the same error for both."""


class NoAccessThroughThisLogin(Exception):
    """Correct password, but no active membership of this kind (staff vs portal)."""


class MembershipNotFound(Exception):
    """Agency selection for an agency the user isn't an active member of."""


@dataclass(frozen=True)
class LoginResult:
    identity_token: str
    memberships: list[MembershipRow]


@dataclass(frozen=True)
class SessionResult:
    session_token: str
    membership: MembershipRow
    expires_in: int


def normalize_email(email: str) -> str:
    # users.email has CHECK (email = lower(email)), so store and look up lowercase.
    return email.strip().lower()


def login(
    conn: Connection, email: str, password: str, kind: LoginKind, settings: Settings
) -> LoginResult:
    user = repository.find_user_by_email(conn, normalize_email(email))
    # Always run bcrypt, even for an unknown email, so timing doesn't reveal
    # which emails have accounts.
    if not verify_password(password, user.password_hash if user else None) or user is None:
        raise InvalidCredentials
    memberships = repository.active_memberships(conn, user.id, is_staff=(kind == "staff"))
    if not memberships:
        raise NoAccessThroughThisLogin
    token = issue_identity_token(
        user.id, kind, settings.session_secret, settings.session_ttl_seconds
    )
    return LoginResult(identity_token=token, memberships=memberships)


def start_session(
    conn: Connection, identity: IdentityClaims, agency_id: uuid.UUID, settings: Settings
) -> SessionResult:
    # agency_id is the user's *choice*; it only counts if they hold an active
    # membership there, of the same kind they logged in with.
    membership = repository.active_membership(
        conn, identity.user_id, agency_id, is_staff=(identity.kind == "staff")
    )
    if membership is None:
        raise MembershipNotFound
    token = issue_session_token(
        identity.user_id, membership.agency_id, settings.session_secret,
        settings.session_ttl_seconds,
    )
    return SessionResult(
        session_token=token, membership=membership, expires_in=settings.session_ttl_seconds
    )
