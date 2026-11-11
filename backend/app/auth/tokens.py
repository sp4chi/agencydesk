"""Signed, expiring tokens. Two kinds, never interchangeable:

* identity token: issued by login. Says "this is user X, who logged in
  through the staff app (or the client portal)". It opens no tenant data;
  it can only be exchanged for a session token via POST /auth/session.
* session token: says "user X, acting in agency Y". This is what
  get_tenant_db accepts.

Format: base64url(json payload) "." base64url(HMAC-SHA256(payload)).
Every payload has a "typ" claim, checked on verify, so an identity token
can't be replayed as a session token or the other way round.

Neither token carries a role or client_id: those are re-read from
agency_memberships when used, so a role change or removal takes effect
immediately.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal

LoginKind = Literal["staff", "client"]


class InvalidToken(Exception):
    """Bad format, bad signature, wrong type, or expired. Callers map this to 401."""


@dataclass(frozen=True)
class SessionClaims:
    user_id: uuid.UUID
    agency_id: uuid.UUID
    expires_at: int


@dataclass(frozen=True)
class IdentityClaims:
    user_id: uuid.UUID
    kind: LoginKind
    expires_at: int


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str, secret: str) -> str:
    return _b64encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())


def _issue(body: dict[str, Any], secret: str, ttl_seconds: int) -> str:
    body = {**body, "exp": int(time.time()) + ttl_seconds}
    payload = _b64encode(json.dumps(body, separators=(",", ":")).encode())
    return f"{payload}.{_sign(payload, secret)}"


def _verify(token: str, secret: str, expected_type: str) -> dict[str, Any]:
    try:
        payload, signature = token.split(".")
    except ValueError:
        raise InvalidToken("malformed") from None
    # Constant-time comparison so the signature can't be guessed byte by byte.
    if not hmac.compare_digest(signature, _sign(payload, secret)):
        raise InvalidToken("bad signature")
    try:
        body = json.loads(_b64decode(payload))
        expires_at = int(body["exp"])
        token_type = body["typ"]
    except (ValueError, KeyError, TypeError):
        raise InvalidToken("bad payload") from None
    if token_type != expected_type:
        raise InvalidToken("wrong token type")
    if expires_at <= time.time():
        raise InvalidToken("expired")
    return body


# ------------------------------------------------------------- session
def issue_session_token(
    user_id: uuid.UUID, agency_id: uuid.UUID, secret: str, ttl_seconds: int
) -> str:
    return _issue(
        {"typ": "session", "sub": str(user_id), "agency": str(agency_id)}, secret, ttl_seconds
    )


def verify_session_token(token: str, secret: str) -> SessionClaims:
    body = _verify(token, secret, "session")
    try:
        return SessionClaims(
            user_id=uuid.UUID(body["sub"]),
            agency_id=uuid.UUID(body["agency"]),
            expires_at=int(body["exp"]),
        )
    except (ValueError, KeyError, TypeError):
        raise InvalidToken("bad payload") from None


# ------------------------------------------------------------ identity
def issue_identity_token(
    user_id: uuid.UUID, kind: LoginKind, secret: str, ttl_seconds: int
) -> str:
    return _issue({"typ": "identity", "sub": str(user_id), "kind": kind}, secret, ttl_seconds)


def verify_identity_token(token: str, secret: str) -> IdentityClaims:
    body = _verify(token, secret, "identity")
    try:
        kind = body["kind"]
        if kind not in ("staff", "client"):
            raise ValueError(kind)
        return IdentityClaims(
            user_id=uuid.UUID(body["sub"]), kind=kind, expires_at=int(body["exp"])
        )
    except (ValueError, KeyError, TypeError):
        raise InvalidToken("bad payload") from None


# -------------------------------------------------------------- invites
# Invite tokens are random, not signed: the database stores only their
# SHA-256 hash (invites.token_hash), so a DB leak hands out no working links.
def new_invite_token() -> tuple[str, str]:
    """Returns (raw token for the link, hash to store)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_invite_token(raw)


def hash_invite_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
