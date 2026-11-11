"""Request/response models for time tracking.

Raw time entries are staff-only (their notes are internal). Client users
only ever get a project total, from app.project_hours().
"""
import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

MAX_MINUTES_PER_ENTRY = 1440  # one day; matches the DB CHECK


class TimeEntryCreate(BaseModel):
    # No user_id: you always log your own time. Unknown fields are a 422.
    model_config = ConfigDict(extra="forbid")

    minutes: int = Field(ge=1, le=MAX_MINUTES_PER_ENTRY)
    entry_date: dt.date | None = None  # defaults to today
    note: str = Field(default="", max_length=2_000)


class TimeEntryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minutes: int | None = Field(default=None, ge=1, le=MAX_MINUTES_PER_ENTRY)
    entry_date: dt.date | None = None
    note: str | None = Field(default=None, max_length=2_000)


class StaffTimeEntry(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    minutes: int
    entry_date: dt.date
    note: str
    created_at: dt.datetime


class ProjectHours(BaseModel):
    """Same shape for staff and clients; the number differs. Staff: all
    tasks. Clients: client-visible tasks only."""
    project_id: uuid.UUID
    total_hours: float
