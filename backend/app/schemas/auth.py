"""Request/response models for login, agency selection and /me."""
import uuid
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["agency_admin", "agency_member", "client_user"]


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class MembershipOption(BaseModel):
    agency_id: uuid.UUID
    agency_name: str
    role: Role
    client_name: str | None


class LoginResponse(BaseModel):
    identity_token: str
    memberships: list[MembershipOption]


class SessionRequest(BaseModel):
    # Which of the caller's own memberships to use. Checked against
    # agency_memberships before any token is issued; never used as context.
    agency_id: uuid.UUID


class SessionResponse(BaseModel):
    session_token: str
    expires_in: int
    membership: MembershipOption


class MeUser(BaseModel):
    id: uuid.UUID
    email: str
    name: str


class MeAgency(BaseModel):
    id: uuid.UUID
    name: str


class MeClient(BaseModel):
    id: uuid.UUID
    name: str


class Me(BaseModel):
    user: MeUser
    agency: MeAgency
    role: Role
    client: MeClient | None
