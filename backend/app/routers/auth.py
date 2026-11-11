"""Login and agency selection. Thin: parse, call the service, map errors.

POST /auth/login          staff app login      -> identity token + staff memberships
POST /auth/portal/login   client portal login  -> identity token + client memberships
POST /auth/session        identity token + {agency_id} -> session token for that membership
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Connection

from app.auth import service
from app.auth.db import get_auth_db
from app.auth.repository import MembershipRow
from app.auth.tokens import IdentityClaims, InvalidToken, LoginKind, verify_identity_token
from app.config import Settings
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MembershipOption,
    SessionRequest,
    SessionResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


def _option(m: MembershipRow) -> MembershipOption:
    return MembershipOption(
        agency_id=m.agency_id, agency_name=m.agency_name, role=m.role, client_name=m.client_name
    )


def _login(body: LoginRequest, kind: LoginKind, request: Request, conn: Connection) -> LoginResponse:
    settings: Settings = request.app.state.settings
    try:
        result = service.login(conn, body.email, body.password, kind, settings)
    except service.InvalidCredentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password") from None
    except service.NoAccessThroughThisLogin:
        other = "client portal" if kind == "staff" else "staff app"
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"This account has no access here. Try the {other}."
        ) from None
    return LoginResponse(
        identity_token=result.identity_token,
        memberships=[_option(m) for m in result.memberships],
    )


@router.post("/login", response_model=LoginResponse)
def staff_login(
    body: LoginRequest, request: Request, conn: Connection = Depends(get_auth_db)
) -> LoginResponse:
    return _login(body, "staff", request, conn)


@router.post("/portal/login", response_model=LoginResponse)
def portal_login(
    body: LoginRequest, request: Request, conn: Connection = Depends(get_auth_db)
) -> LoginResponse:
    return _login(body, "client", request, conn)


def require_identity(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)
) -> IdentityClaims:
    settings: Settings = request.app.state.settings
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        return verify_identity_token(credentials.credentials, settings.session_secret)
    except InvalidToken:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated") from None


@router.post("/session", response_model=SessionResponse)
def select_agency(
    body: SessionRequest,
    request: Request,
    identity: IdentityClaims = Depends(require_identity),
    conn: Connection = Depends(get_auth_db),
) -> SessionResponse:
    settings: Settings = request.app.state.settings
    try:
        result = service.start_session(conn, identity, body.agency_id, settings)
    except service.MembershipNotFound:
        # 404, not 403: don't confirm whether that agency exists.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from None
    return SessionResponse(
        session_token=result.session_token,
        expires_in=result.expires_in,
        membership=_option(result.membership),
    )
