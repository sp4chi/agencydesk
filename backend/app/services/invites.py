"""Invite management rules (admin side). Accepting an invite is in
app/auth/service.py, because it runs before the invitee has a tenant."""
import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.auth.tokens import new_invite_token
from app.config import Settings
from app.db import TenantDb
from app.errors import FOREIGN_KEY_VIOLATION, Conflict, Forbidden, Invalid, NotFound, sqlstate
from app.repositories import invites as repository
from app.repositories.invites import InviteRow


@dataclass(frozen=True)
class IssuedInvite:
    invite: InviteRow
    # The raw token, returned to the admin exactly once as part of a link.
    # Only its hash is stored. Never log this.
    invite_url: str


def _require_admin(db: TenantDb) -> None:
    # RLS (invites `admin` policy) already blocks non-admins; this gives a
    # clear 403 instead of an empty list or a database error.
    if db.role != "agency_admin":
        raise Forbidden("Only agency admins can manage invites")


def _invite_url(settings: Settings, raw_token: str) -> str:
    # Token in the URL fragment (#), which browsers don't send to servers or
    # in Referer headers, so it doesn't end up in access logs.
    return f"{settings.app_base_url}/invite#token={raw_token}"


def list_invites(db: TenantDb) -> list[InviteRow]:
    _require_admin(db)
    return repository.list_invites(db.conn)


def create_invite(
    db: TenantDb, settings: Settings, email: str, role: str, client_id: uuid.UUID | None
) -> IssuedInvite:
    _require_admin(db)
    email = email.strip().lower()
    if "@" not in email:
        raise Invalid("Enter a valid email address")
    if (role == "client_user") != (client_id is not None):
        raise Invalid("client_id is required for client users and not allowed for staff")
    if repository.is_active_member(db.conn, email):
        raise Conflict("This person is already a member of the agency")

    raw, token_hash = new_invite_token()
    try:
        invite = repository.upsert_pending_invite(
            db.conn, db.agency_id, db.user_id, email, role, client_id, token_hash,
            settings.invite_ttl_days,
        )
    except IntegrityError as exc:
        if sqlstate(exc) == FOREIGN_KEY_VIOLATION:
            # The composite FK (agency_id, client_id) rejects other tenants' clients too.
            raise Invalid("Unknown client") from None
        raise
    return IssuedInvite(invite=invite, invite_url=_invite_url(settings, raw))


def resend_invite(db: TenantDb, settings: Settings, invite_id: uuid.UUID) -> IssuedInvite:
    _require_admin(db)
    raw, token_hash = new_invite_token()
    invite = repository.resend_pending_invite(
        db.conn, invite_id, token_hash, settings.invite_ttl_days
    )
    if invite is None:
        _raise_missing_or_not_pending(db, invite_id)
    return IssuedInvite(invite=invite, invite_url=_invite_url(settings, raw))


def revoke_invite(db: TenantDb, invite_id: uuid.UUID) -> None:
    _require_admin(db)
    if not repository.revoke_pending_invite(db.conn, invite_id):
        _raise_missing_or_not_pending(db, invite_id)


def _raise_missing_or_not_pending(db: TenantDb, invite_id: uuid.UUID) -> None:
    if repository.invite_exists(db.conn, invite_id):  # under RLS: only this agency's
        raise Conflict("This invite is no longer pending")
    raise NotFound()
