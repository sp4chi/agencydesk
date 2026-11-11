"""Request/response models for invites. Never expose token_hash."""
import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.auth import Role


class InviteCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: Role
    client_id: uuid.UUID | None = None


class StaffInvite(BaseModel):
    id: uuid.UUID
    email: str
    role: Role
    client_id: uuid.UUID | None
    status: Literal["pending", "accepted", "revoked"]
    send_count: int
    expires_at: dt.datetime
    created_at: dt.datetime


class IssuedInviteResponse(BaseModel):
    invite: StaffInvite
    # Shown to the admin once, to pass on to the invitee (no email sending in scope).
    invite_url: str


class InviteAccept(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    # Only for creating a new account; ignored when accepting while logged in.
    name: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=200)


class InviteAccepted(BaseModel):
    agency_id: uuid.UUID
    role: Role
    # Which login to use next: the staff app or the client portal.
    login: Literal["staff", "portal"]
