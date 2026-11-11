"""Login, agency selection and invite acceptance rules. No HTTP here: the router maps the
exceptions below to status codes."""
import uuid
from dataclasses import dataclass

from sqlalchemy import Connection
from sqlalchemy.exc import DBAPIError

from app.auth import repository
from app.auth.passwords import hash_password, verify_password
from app.auth.repository import MembershipRow
from app.auth.tokens import (
    IdentityClaims,
    LoginKind,
    hash_invite_token,
    issue_identity_token,
    issue_session_token,
)
from app.config import Settings
from app.errors import Forbidden, Invalid, NotAuthenticated, NotFound


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


# ------------------------------------------------------------ invites
MIN_PASSWORD_LENGTH = 8


def accept_invite(
    conn: Connection,
    raw_token: str,
    identity: IdentityClaims | None,
    name: str | None,
    password: str | None,
) -> repository.AcceptedInvite:
    """Accept an invite.

    Logged in (identity given): attaches the membership to that account, but
    only if it is the invited email (app.accept_invite checks this).
    Logged out: creates a new account with name + password, but only if no
    account exists for the invited email yet.
    """
    password_hash = None
    if identity is None and password is not None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise Invalid(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
        try:
            password_hash = hash_password(password)
        except ValueError as exc:  # over bcrypt's 72-byte limit
            raise Invalid(str(exc)) from None

    try:
        return repository.accept_invite(
            conn,
            hash_invite_token(raw_token),
            identity.user_id if identity else None,
            name if identity is None else None,
            password_hash,
        )
    except DBAPIError as exc:
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate == "P0002":
            raise NotFound("This invite is invalid, expired or already used") from None
        if sqlstate == "28000":
            if identity is None:
                raise NotAuthenticated(
                    "An account with this email already exists. Log in to accept the invite."
                ) from None
            raise Forbidden("You're logged in as a different account than this invite is for.") from None
        if sqlstate == "22023":
            raise Invalid("Name and password are required to create an account") from None
        raise
