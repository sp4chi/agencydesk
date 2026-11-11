"""Request/response models for tasks.

StaffTask vs ClientTask: RLS already hides internal *tasks* from clients;
ClientTask also hides internal *fields* (visibility, assignee, creator),
so a client response can't leak them even if a query changes.
"""
import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TaskStatus = Literal["todo", "in_progress", "in_review", "done"]
TaskPriority = Literal["low", "medium", "high", "urgent"]
Visibility = Literal["internal", "client"]


class TaskCreate(BaseModel):
    # Unknown fields (agency_id, project_id, created_by, ...) are an error, not ignored.
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20_000)
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"
    # Internal unless someone deliberately shares it (fail closed).
    visibility: Visibility = "internal"
    assignee_user_id: uuid.UUID | None = None
    due_date: dt.date | None = None


class TaskUpdate(BaseModel):
    """Every field optional; only the fields sent are changed. Send
    `"assignee_user_id": null` to unassign, `"due_date": null` to clear.
    A task can't be moved to another project: project_id is rejected."""
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    visibility: Visibility | None = None
    assignee_user_id: uuid.UUID | None = None
    due_date: dt.date | None = None


class StaffTask(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    visibility: Visibility
    assignee_user_id: uuid.UUID | None
    assignee_name: str | None
    due_date: dt.date | None
    created_by: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime


class ClientTask(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    due_date: dt.date | None
    created_at: dt.datetime
    updated_at: dt.datetime
