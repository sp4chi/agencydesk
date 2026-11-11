"""Request/response models for task comments."""
import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.tasks import Visibility


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=10_000)
    # Staff only. Defaults to internal (fail closed). For client users it is
    # always forced to "client", whatever they send.
    visibility: Visibility = "internal"


class StaffComment(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    body: str
    visibility: Visibility
    # True only if the comment AND its task are client-visible: what the
    # client actually sees. Lets the UI warn "this won't reach the client".
    visible_to_client: bool
    author_user_id: uuid.UUID
    author_name: str
    created_at: dt.datetime


class ClientComment(BaseModel):
    id: uuid.UUID
    body: str
    author_name: str
    created_at: dt.datetime
