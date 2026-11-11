"""Request/response models for task files.

Neither response model includes storage_key: where the bytes live is
never exposed. Downloads go through GET /files/{id}/download only.
"""
import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.tasks import Visibility

ApprovalStatus = Literal["pending", "approved", "changes_requested"]


class FileUpdate(BaseModel):
    """Staff only: rename or change who can see the file."""
    model_config = ConfigDict(extra="forbid")

    filename: str | None = Field(default=None, min_length=1, max_length=255)
    visibility: Visibility | None = None


class FileReview(BaseModel):
    """Client users only: their decision on a client-visible file."""
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "changes_requested"]


class StaffFile(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    visibility: Visibility
    # True only if the file AND its task are client-visible.
    visible_to_client: bool
    approval_status: ApprovalStatus
    reviewed_by: uuid.UUID | None
    reviewed_by_name: str | None
    reviewed_at: dt.datetime | None
    uploaded_by: uuid.UUID
    uploaded_by_name: str
    created_at: dt.datetime


class ClientFile(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    approval_status: ApprovalStatus
    reviewed_at: dt.datetime | None
    created_at: dt.datetime
