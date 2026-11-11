"""Session tokens: a signed, expiring claim of (user_id, agency_id).

Format: base64url(json payload) "." base64url(HMAC-SHA256(payload)).

The token only says *who* and *which agency*. It deliberately carries no
role or client_id: get_tenant_db re-reads those from agency_memberships on
every request, so a role change or removal takes effect immediately.
Issuing tokens (login / agency selection) is step 6; this module is shared.
"""
import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass


class InvalidToken(Exception):
    """Bad format, bad signature, or expired. Callers map this to 401."""


@dataclass(frozen=True)
class SessionClaims:
    user_id: uuid.UUID
    agency_id: uuid.UUID
    expires_at: int


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str, secret: str) -> str:
    return _b64encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())


def issue_session_token(
    user_id: uuid.UUID, agency_id: uuid.UUID, secret: str, ttl_seconds: int
) -> str:
    body = {"sub": str(user_id), "agency": str(agency_id), "exp": int(time.time()) + ttl_seconds}
    payload = _b64encode(json.dumps(body, separators=(",", ":")).encode())
    return f"{payload}.{_sign(payload, secret)}"


def verify_session_token(token: str, secret: str) -> SessionClaims:
    try:
        payload, signature = token.split(".")
    except ValueError:
        raise InvalidToken("malformed") from None
    # Constant-time comparison so the signature can't be guessed byte by byte.
    if not hmac.compare_digest(signature, _sign(payload, secret)):
        raise InvalidToken("bad signature")
    try:
        body = json.loads(_b64decode(payload))
        claims = SessionClaims(
            user_id=uuid.UUID(body["sub"]),
            agency_id=uuid.UUID(body["agency"]),
            expires_at=int(body["exp"]),
        )
    except (ValueError, KeyError, TypeError):
        raise InvalidToken("bad payload") from None
    if claims.expires_at <= time.time():
        raise InvalidToken("expired")
    return claims
